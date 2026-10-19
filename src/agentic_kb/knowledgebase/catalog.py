"""Auto-generated schema catalog.

Builds a human-reviewable `catalog.yaml` from a live database:

* reflected structure (types, keys, comments) - always read live, never stored as truth
* profiled column facts: distinct values of low-cardinality columns, min/max of numbers and dates
* inferred relations for columns that look like foreign keys but have no declared constraint
* LLM-written descriptions for tables/columns that have no database comment

The file is meant to be generated once, reviewed/edited by a developer, and then loaded at runtime
(`knowledgebase.catalog_file`) so the SQL prompt carries the extra context.
Entries a human has edited are preserved when the catalog is regenerated.
"""

import fnmatch
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml
from pydantic import BaseModel, Field

from agentic_kb.database.base import BaseDatabaseProvider
from agentic_kb.database.models import ColumnMetadata, DatabaseSchemaMetadata, TableMetadata
from agentic_kb.exceptions.errors import LLMRateLimitError
from agentic_kb.llm.base import BaseLLMProvider, LLMMessage
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.knowledgebase.catalog")

CATALOG_VERSION = 1
MAX_DISTINCT_VALUES = 20
MAX_VALUE_LENGTH = 40
SAMPLE_ROWS_FOR_LLM = 3

HEADER = """\
# ----------------------------------------------------------------------------------------------
# Agentic KB schema catalog  (generated - REVIEW BEFORE USE)
#
# How to review:
#   * Entries marked `needs_review: true` were written automatically (LLM descriptions, inferred
#     relations). Fix the text if it is wrong, then delete the `needs_review` line (or set false).
#   * Edit any `description` freely - edited entries are kept when you regenerate.
#   * Add business meaning the database can't tell: what status codes mean, units, etc.
#   * Add/remove `relations` by hand. Declared foreign keys are read from the DB and not listed.
#   * `values` / `range` are profiled facts and refreshed on every generate.
#   * Preview exactly what the LLM will see:  agentic-kb catalog show -c <config>
# ----------------------------------------------------------------------------------------------
"""


class _TableDocs(BaseModel):
    table_description: str = Field(..., description="One or two sentences on what the table holds")
    columns: Dict[str, str] = Field(default_factory=dict, description="column name -> short meaning")


# --------------------------------------------------------------------------- helpers
def _is_excluded(column: str, patterns: List[str]) -> bool:
    low = column.lower()
    return any(fnmatch.fnmatch(low, p.lower()) for p in patterns)


def _type_family(data_type: str) -> str:
    t = data_type.lower()
    if "uuid" in t:
        return "uuid"
    if "array" in t or "[]" in t or "json" in t or "bytea" in t or "blob" in t:
        return "complex"
    if "bool" in t or t == "bit":
        return "bool"
    if "int" in t or "serial" in t:
        return "int"
    if any(k in t for k in ("numeric", "decimal", "float", "double", "real", "money")):
        return "number"
    if any(k in t for k in ("timestamp", "date", "time")):
        return "datetime"
    if "text" in t:
        return "text"  # free text: never profiled
    if any(k in t for k in ("char", "string", "enum", "citext")):
        return "str"
    return "other"


def _short(value: Any) -> str:
    s = str(value)
    return s if len(s) <= MAX_VALUE_LENGTH else s[: MAX_VALUE_LENGTH - 1] + "…"


class _Sql:
    """Dialect-aware identifier quoting for the handful of profiling queries."""

    def __init__(self, dialect: str):
        self.mssql = dialect.lower() in ("sqlserver", "mssql", "tsql")

    def ident(self, name: str) -> str:
        return f"[{name}]" if self.mssql else '"' + name.replace('"', '""') + '"'

    def table(self, t: TableMetadata) -> str:
        return f"{self.ident(t.schema_name)}.{self.ident(t.table_name)}"

    def limit(self, query_body: str, n: int) -> str:
        if self.mssql:
            return query_body.replace("SELECT ", f"SELECT TOP {n} ", 1)
        return f"{query_body} LIMIT {n}"


# --------------------------------------------------------------------------- builder
class CatalogBuilder:
    """Creates the catalog dict (see module docstring) from a live database."""

    def __init__(
        self,
        db: BaseDatabaseProvider,
        schema: DatabaseSchemaMetadata,
        llm: Optional[BaseLLMProvider] = None,
        exclude_columns: Optional[List[str]] = None,
        table_descriptions: Optional[Dict[str, str]] = None,
        log: Callable[[str], None] = lambda msg: None,
    ):
        self.db = db
        self.schema = schema
        self.llm = llm
        self.exclude = exclude_columns or []
        self.config_table_descriptions = table_descriptions or {}
        self.log = log
        self.sql = _Sql(db.dialect_name)
        self.review: List[str] = []
        self.warnings: List[str] = []

    # ---- db helper
    def _query(self, sql: str, timeout: float = 15.0) -> List[Dict[str, Any]]:
        try:
            return self.db.execute(sql, max_rows=1000, timeout_seconds=timeout).rows
        except Exception as e:  # profiling is best-effort; never fail the whole build
            logger.debug(f"Profiling query failed ({sql[:80]}...): {e}")
            return []

    # ---- profiling
    def _row_count(self, t: TableMetadata) -> Optional[int]:
        rows = self._query(f"SELECT COUNT(*) AS n FROM {self.sql.table(t)}")
        return int(next(iter(rows[0].values()))) if rows else None

    def _profile_values(self, t: TableMetadata, c: ColumnMetadata, row_count: Optional[int]) -> Optional[List[str]]:
        """Distinct values if the column is low-cardinality (enum-like), else None."""
        family = _type_family(c.data_type)
        if family not in ("str", "int", "bool") or c.is_primary_key or c.is_foreign_key:
            return None
        if not row_count:
            return None
        col, tbl = self.sql.ident(c.name), self.sql.table(t)
        body = (
            f"SELECT {col} AS v, COUNT(*) AS n FROM {tbl} WHERE {col} IS NOT NULL "
            f"GROUP BY {col} ORDER BY n DESC, {col}"
        )
        rows = self._query(self.sql.limit(body, MAX_DISTINCT_VALUES + 1))
        distinct = len(rows)
        # Skip high-cardinality columns and (near-)unique ones such as codes and numbers
        if distinct == 0 or distinct > MAX_DISTINCT_VALUES or distinct > max(1, row_count // 2):
            return None
        if family == "int" and distinct > 10:
            return None
        # A single value in a small table is just that table's contents, not a category
        if distinct < 2 and row_count < 20:
            return None
        return [_short(r["v"]) for r in rows]

    def _profile_ranges(self, t: TableMetadata, row_count: Optional[int]) -> Dict[str, List[str]]:
        cols = [
            c for c in t.columns
            if _type_family(c.data_type) in ("int", "number", "datetime")
            and not c.is_primary_key and not c.is_foreign_key and not _is_excluded(c.name, self.exclude)
        ]
        if not cols or not row_count:
            return {}
        exprs = ", ".join(
            f"MIN({self.sql.ident(c.name)}) AS {self.sql.ident('min_' + str(i))}, "
            f"MAX({self.sql.ident(c.name)}) AS {self.sql.ident('max_' + str(i))}"
            for i, c in enumerate(cols)
        )
        rows = self._query(f"SELECT {exprs} FROM {self.sql.table(t)}")
        if not rows:
            return {}
        r = rows[0]
        out: Dict[str, List[str]] = {}
        for i, c in enumerate(cols):
            lo, hi = r.get(f"min_{i}"), r.get(f"max_{i}")
            if lo is not None and hi is not None:
                out[c.name] = [_short(lo), _short(hi)]
        return out

    # ---- relation inference
    def _infer_relations(self, t: TableMetadata, row_counts: Dict[str, Optional[int]]) -> List[Dict[str, Any]]:
        found: List[Dict[str, Any]] = []
        pk_tables = [
            (other, other.columns[[c.name for c in other.columns].index(other.primary_keys[0])])
            for other in self.schema.tables.values()
            if other.full_name != t.full_name and len(other.primary_keys) == 1
            and other.primary_keys[0] in [c.name for c in other.columns]
        ]
        for c in t.columns:
            if c.is_foreign_key or c.is_primary_key:
                continue
            m = re.fullmatch(r"(.+?)_?id", c.name, re.I)  # xxxId / xxx_id (not a bare "id")
            if not m:
                continue
            base = m.group(1).strip("_").lower()
            family = _type_family(c.data_type)
            candidates = [(o, pk) for o, pk in pk_tables if _type_family(pk.data_type) == family]
            by_name = [
                (o, pk) for o, pk in candidates
                if base and o.table_name.lower() in (base, base + "s", base.rstrip("s"), base + "es")
            ]
            chosen: Optional[Tuple[TableMetadata, ColumnMetadata]] = None
            how = ""
            if len(by_name) == 1:
                chosen, how = by_name[0], "name match"
                if self._contained(t, c, *chosen) is False:
                    chosen = None  # name matched but values don't - don't claim a relation
            elif not by_name and len(candidates) == 1:
                o, pk = candidates[0]
                if self._contained(t, c, o, pk) is True:
                    chosen, how = candidates[0], "values match the only compatible key"
            if chosen:
                o, pk = chosen
                found.append({
                    "column": c.name,
                    "references": f"{o.full_name}.{pk.name}",
                    "inferred": True,
                    "reason": how,
                    "needs_review": True,
                })
        return found

    def _contained(self, t: TableMetadata, c: ColumnMetadata, o: TableMetadata, pk: ColumnMetadata) -> Optional[bool]:
        """True if every distinct non-null value of t.c exists in o.pk; None if there is no data to judge."""
        body = (
            f"SELECT COUNT(*) AS total, COUNT(b.{self.sql.ident(pk.name)}) AS matched FROM "
            f"(SELECT DISTINCT {self.sql.ident(c.name)} AS v FROM {self.sql.table(t)} "
            f"WHERE {self.sql.ident(c.name)} IS NOT NULL {{limit}}) a "
            f"LEFT JOIN {self.sql.table(o)} b ON b.{self.sql.ident(pk.name)} = a.v"
        )
        if self.sql.mssql:
            body = body.replace("SELECT DISTINCT", "SELECT DISTINCT TOP 1000", 1).replace("{limit}", "")
        else:
            body = body.replace("{limit}", "LIMIT 1000")
        rows = self._query(body)
        if not rows:
            return None
        total, matched = int(rows[0]["total"]), int(rows[0]["matched"])
        if total == 0:
            return None
        return matched == total

    # ---- LLM descriptions
    def _sample_rows(self, t: TableMetadata) -> List[Dict[str, str]]:
        cols = [c for c in t.columns if not _is_excluded(c.name, self.exclude)
                and _type_family(c.data_type) not in ("complex",)]
        if not cols:
            return []
        select = ", ".join(self.sql.ident(c.name) for c in cols)
        rows = self._query(self.sql.limit(f"SELECT {select} FROM {self.sql.table(t)}", SAMPLE_ROWS_FOR_LLM))
        return [{k: _short(v) for k, v in r.items()} for r in rows]

    def _describe(self, t: TableMetadata, entry: Dict[str, Any], with_rows: bool) -> Optional[_TableDocs]:
        lines = [f"Table: {t.full_name}"]
        for c in t.columns:
            col_entry = entry["columns"].get(c.name, {})
            extra = ""
            if col_entry.get("values"):
                extra = f"  [values: {col_entry['values']}]"
            elif col_entry.get("range"):
                extra = f"  [range: {col_entry['range']}]"
            lines.append(f"  - {c.to_ddl_fragment()}{extra}")
        if with_rows:
            rows = self._sample_rows(t)
            if rows:
                lines.append(f"Sample rows: {rows}")
        prompt = (
            "You document database tables for a text-to-SQL assistant. Given the table below, write a "
            "concise table description and a short meaning (max 12 words) for each column that is not "
            "self-explanatory. Mention units, status meanings, and relations when evident. Do not invent "
            "facts you cannot infer; omit columns you are unsure about.\n\n" + "\n".join(lines)
        )
        assert self.llm is not None
        return self.llm.generate_structured(
            messages=[LLMMessage.system("You are a precise data documentation assistant."), LLMMessage.user(prompt)],
            response_model=_TableDocs,
            temperature=0.0,
        )

    # ---- main
    def build(
        self,
        existing: Optional[Dict[str, Any]] = None,
        profile_values: bool = True,
        use_llm: bool = True,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        is_document_db = self.db.dialect_name == "mongodb"
        if is_document_db and profile_values:
            # Profiling and relation inference are SQL queries; fields/types already come from sampling
            self.log("MongoDB: SQL value profiling and relation inference are skipped (schema comes from sampling).")
            profile_values = False
        existing_tables = (existing or {}).get("tables", {}) if not overwrite else {}
        tables_out: Dict[str, Any] = {}
        row_counts: Dict[str, Optional[int]] = {}
        llm_ok = use_llm and self.llm is not None

        for full_name, t in self.schema.tables.items():
            self.log(f"  - {full_name}")
            old = existing_tables.get(full_name, {}) or {}
            old_cols = old.get("columns", {}) or {}
            row_count = self._row_count(t) if profile_values else (t.estimated_row_count if is_document_db else None)
            row_counts[full_name] = row_count
            ranges = self._profile_ranges(t, row_count) if profile_values else {}

            entry: Dict[str, Any] = {"description": old.get("description") or t.description or self.config_table_descriptions.get(full_name) or self.config_table_descriptions.get(t.table_name)}
            if old.get("needs_review") and old.get("description"):
                entry["needs_review"] = True
            if row_count is not None:
                entry["row_count"] = row_count
            entry["columns"] = {}

            for c in t.columns:
                prev = old_cols.get(c.name, {}) or {}
                ce: Dict[str, Any] = {"type": c.data_type}
                desc = prev.get("description") or c.description
                if desc:
                    ce["description"] = desc
                    if prev.get("needs_review"):
                        ce["needs_review"] = True
                if profile_values and not _is_excluded(c.name, self.exclude):
                    values = self._profile_values(t, c, row_count)
                    if values:
                        ce["values"] = values
                    elif c.name in ranges:
                        ce["range"] = ranges[c.name]
                elif profile_values:
                    ce["skipped"] = "excluded by catalog_exclude_columns"
                entry["columns"][c.name] = ce

            # relations: keep what a human has in the file, add newly inferred ones
            relations = list(old.get("relations", []) or [])
            known = {r.get("column") for r in relations}
            for r in ([] if is_document_db else self._infer_relations(t, row_counts)):
                if r["column"] not in known:
                    relations.append(r)
            if relations:
                entry["relations"] = relations
            tables_out[full_name] = entry

        # LLM descriptions for whatever is still undocumented
        if llm_ok:
            self.log("Writing missing descriptions with the LLM ...")
            for full_name, t in self.schema.tables.items():
                entry = tables_out[full_name]
                missing_table = not entry.get("description")
                missing_cols = [c.name for c in t.columns if not entry["columns"][c.name].get("description")]
                if not missing_table and not missing_cols:
                    continue
                try:
                    docs = self._describe(t, entry, with_rows=profile_values)
                except LLMRateLimitError as e:
                    self.warnings.append(
                        f"LLM rate limit reached - descriptions skipped from {full_name} onward. "
                        f"Re-run later or write them by hand. ({e.user_safe_message})"
                    )
                    break
                except Exception as e:
                    self.warnings.append(f"Could not describe {full_name}: {e}")
                    continue
                if docs is None:
                    continue
                if missing_table and docs.table_description:
                    entry["description"] = docs.table_description.strip()
                    entry["needs_review"] = True
                lowered = {k.lower(): v for k, v in docs.columns.items()}
                for name in missing_cols:
                    text = lowered.get(name.lower())
                    if text:
                        entry["columns"][name]["description"] = text.strip()
                        entry["columns"][name]["needs_review"] = True

        # Review list for the CLI summary
        for full_name, entry in tables_out.items():
            if entry.get("needs_review"):
                self.review.append(f"{full_name}: table description (auto-written)")
            for cname, ce in entry["columns"].items():
                if ce.get("needs_review"):
                    self.review.append(f"{full_name}.{cname}: description (auto-written)")
            for r in entry.get("relations", []):
                if r.get("needs_review"):
                    self.review.append(f"{full_name}.{r['column']} -> {r['references']} (inferred: {r.get('reason', '')})")
            if not entry.get("description"):
                entry.pop("description")

        return {
            "version": CATALOG_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "database": self.schema.database_name,
            "dialect": self.schema.dialect,
            "tables": tables_out,
        }


# --------------------------------------------------------------------------- file io
def dump_catalog(catalog: Dict[str, Any], path: Path) -> None:
    body = yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True, width=100)
    Path(path).write_text(HEADER + "\n" + body, encoding="utf-8")


def load_catalog(path: Path) -> Optional[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return None
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else None


def apply_catalog(
    schema: DatabaseSchemaMetadata,
    catalog: Optional[Dict[str, Any]],
    table_descriptions: Optional[Dict[str, str]] = None,
) -> DatabaseSchemaMetadata:
    """Merge catalog (and config table descriptions) into reflected metadata. Mutates and returns `schema`."""
    table_descriptions = table_descriptions or {}
    cat_tables = (catalog or {}).get("tables", {}) or {}

    for full_name, t in schema.tables.items():
        entry = cat_tables.get(full_name) or {}
        desc = (
            table_descriptions.get(full_name)
            or table_descriptions.get(t.table_name)
            or entry.get("description")
        )
        if desc:
            t.description = desc

        col_entries = entry.get("columns", {}) or {}
        by_lower = {c.name.lower(): c for c in t.columns}
        for cname, ce in col_entries.items():
            col = by_lower.get(str(cname).lower())
            if col is None or not isinstance(ce, dict):
                continue  # column no longer exists in the DB
            if ce.get("description"):
                col.description = ce["description"]
            if ce.get("values"):
                col.sample_values = [str(v) for v in ce["values"]]
            elif ce.get("range"):
                col.value_range = [str(v) for v in ce["range"]]

        for rel in entry.get("relations", []) or []:
            col = by_lower.get(str(rel.get("column", "")).lower())
            ref = str(rel.get("references", ""))
            if col is None or col.is_foreign_key or "." not in ref:
                continue  # declared FK in the DB wins
            ref_table, ref_col = ref.rsplit(".", 1)
            col.is_foreign_key = True
            col.foreign_table = ref_table
            col.foreign_column = ref_col
            col.fk_inferred = True
    return schema
