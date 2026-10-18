"""Tests for the auto-generated schema catalog (profiling, inference, merge, preservation)."""

import sqlite3
from types import SimpleNamespace

import pytest

from agentic_kb.database.models import ColumnMetadata, DatabaseSchemaMetadata, TableMetadata
from agentic_kb.knowledgebase.catalog import (
    CatalogBuilder,
    apply_catalog,
    dump_catalog,
    load_catalog,
)
from agentic_kb.llm.mock import MockLLMProvider


class SqliteDB:
    """Minimal DB double backed by in-memory SQLite (same quoting/LIMIT syntax as the profiler emits)."""

    dialect_name = "sqlite"

    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, name TEXT);
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY, customerId INTEGER, status TEXT, total REAL, ref TEXT, note TEXT);
            INSERT INTO users VALUES (1,'a@x.com','Ann'),(2,'b@x.com','Bob'),(3,'c@x.com','Cy');
            """
        )
        for i in range(12):
            self.conn.execute(
                "INSERT INTO orders VALUES (?,?,?,?,?,?)",
                (i + 1, (i % 3) + 1, "paid" if i % 2 else "pending", 10.0 + i, f"REF{i}", f"free text {i}"),
            )

    def execute(self, sql, params=None, max_rows=None, timeout_seconds=None):
        cur = self.conn.execute(sql.replace('"main".', ""))
        return SimpleNamespace(rows=[dict(r) for r in cur.fetchall()])


def _schema() -> DatabaseSchemaMetadata:
    def col(name, typ, **kw):
        return ColumnMetadata(name=name, data_type=typ, **kw)

    users = TableMetadata(
        schema_name="main", table_name="users", full_name="main.users",
        columns=[col("id", "INTEGER", is_primary_key=True), col("email", "TEXT"), col("name", "VARCHAR")],
        primary_keys=["id"],
    )
    orders = TableMetadata(
        schema_name="main", table_name="orders", full_name="main.orders",
        columns=[
            col("id", "INTEGER", is_primary_key=True), col("customerId", "INTEGER"),
            col("status", "VARCHAR"), col("total", "NUMERIC"), col("ref", "VARCHAR"), col("note", "TEXT"),
        ],
        primary_keys=["id"],
    )
    return DatabaseSchemaMetadata(
        dialect="sqlite", database_name="t", tables={"main.users": users, "main.orders": orders}
    )


def _builder(llm=None):
    return CatalogBuilder(
        db=SqliteDB(), schema=_schema(), llm=llm,
        exclude_columns=["*email*"], table_descriptions={},
    )


def test_profiles_enum_like_columns_and_ranges():
    cat = _builder().build(use_llm=False)
    cols = cat["tables"]["main.orders"]["columns"]

    assert sorted(cols["status"]["values"]) == ["paid", "pending"]
    assert "values" not in cols["ref"]            # unique codes are not categories
    assert "values" not in cols["note"]           # free text is never profiled
    assert cols["total"]["range"] == ["10.0", "21.0"]
    assert cat["tables"]["main.orders"]["row_count"] == 12


def test_sensitive_columns_are_never_profiled():
    cat = _builder().build(use_llm=False)
    email = cat["tables"]["main.users"]["columns"]["email"]
    assert "values" not in email and "range" not in email
    assert "excluded" in email["skipped"]


def test_infers_relation_from_values_when_name_gives_no_hint():
    cat = _builder().build(use_llm=False)
    rels = cat["tables"]["main.orders"]["relations"]
    assert rels == [{
        "column": "customerId", "references": "main.users.id", "inferred": True,
        "reason": "values match the only compatible key", "needs_review": True,
    }]


def test_infers_relation_by_name():
    b = _builder()
    b.db.conn.execute("ALTER TABLE orders RENAME COLUMN customerId TO userId")
    for c in b.schema.tables["main.orders"].columns:
        if c.name == "customerId":
            c.name = "userId"
    rels = b.build(use_llm=False)["tables"]["main.orders"]["relations"]
    assert rels[0]["references"] == "main.users.id" and rels[0]["reason"] == "name match"


def test_no_relation_claimed_when_values_do_not_match():
    b = _builder()
    b.db.conn.execute("UPDATE orders SET customerId = 99")
    assert "relations" not in b.build(use_llm=False)["tables"]["main.orders"]


def test_llm_descriptions_are_flagged_for_review():
    llm = MockLLMProvider(default_response=(
        '{"table_description": "Customer orders.", "columns": {"status": "Payment state", "total": "Order value"}}'
    ))
    b = _builder(llm)
    cat = b.build(use_llm=True)

    orders = cat["tables"]["main.orders"]
    assert orders["description"] == "Customer orders." and orders["needs_review"] is True
    assert orders["columns"]["status"] == {**orders["columns"]["status"], "description": "Payment state", "needs_review": True}
    assert any("main.orders.status" in item for item in b.review)


def test_regenerate_keeps_human_edits_but_refreshes_profile(tmp_path):
    path = tmp_path / "catalog.yaml"
    first = _builder().build(use_llm=False)
    first["tables"]["main.orders"]["description"] = "Hand written."
    first["tables"]["main.orders"]["columns"]["status"]["description"] = "paid = settled"
    dump_catalog(first, path)

    b = _builder()
    b.db.conn.execute("INSERT INTO orders VALUES (100, 1, 'refunded', 5.0, 'REFX', 'n')")
    second = b.build(existing=load_catalog(path), use_llm=False)

    orders = second["tables"]["main.orders"]
    assert orders["description"] == "Hand written."
    assert orders["columns"]["status"]["description"] == "paid = settled"
    assert "refunded" in orders["columns"]["status"]["values"]       # profile refreshed
    assert not [i for i in b.review if "description" in i]            # human text isn't flagged


def test_overwrite_discards_existing_edits(tmp_path):
    existing = _builder().build(use_llm=False)
    existing["tables"]["main.orders"]["description"] = "Hand written."
    fresh = _builder().build(existing=existing, use_llm=False, overwrite=True)
    assert "description" not in fresh["tables"]["main.orders"]


def test_apply_catalog_merges_into_prompt_context():
    cat = _builder().build(use_llm=False)
    cat["tables"]["main.orders"]["description"] = "All customer orders."
    cat["tables"]["main.orders"]["columns"]["status"]["description"] = "Payment state"

    schema = apply_catalog(_schema(), cat)
    text = schema.to_prompt_context(["main.orders"])

    assert "All customer orders." in text
    assert "status VARCHAR -- Payment state; values: 'paid', 'pending'" in text
    assert '"customerId" INTEGER REFERENCES main.users(id) (inferred)' in text


def test_apply_catalog_ignores_unknown_columns_and_keeps_declared_fk():
    schema = _schema()
    declared = schema.tables["main.orders"].columns[1]
    declared.is_foreign_key, declared.foreign_table, declared.foreign_column = True, "main.other", "pk"
    catalog = {"tables": {"main.orders": {
        "columns": {"ghost": {"description": "gone"}},
        "relations": [{"column": "customerId", "references": "main.users.id"}],
    }}}
    apply_catalog(schema, catalog)
    assert declared.foreign_table == "main.other" and not declared.fk_inferred


def test_missing_catalog_file_returns_none(tmp_path):
    assert load_catalog(tmp_path / "nope.yaml") is None


def test_config_table_descriptions_reach_the_prompt():
    schema = apply_catalog(_schema(), None, {"main.users": "Registered users."})
    assert "Registered users." in schema.to_prompt_context(["main.users"])
