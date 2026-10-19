"""Identifier case and quoting fixes for generated SQL (PostgreSQL, MySQL, SQL Server).

PostgreSQL folds unquoted identifiers to lower case, so a column created as "carNo" must be
referenced as "carNo". LLMs routinely emit `carNo` unquoted, which then fails with
`column "carno" does not exist`. This module rewrites table and column references to the exact
spelling found in the discovered schema and quotes them when the spelling is not all lower case.
"""

from typing import Dict, Set

import sqlglot
from sqlglot import exp

from agentic_kb.database.models import DatabaseSchemaMetadata
from agentic_kb.observability.logging import get_logger
from agentic_kb.security.dialects import sqlglot_dialect

logger = get_logger("agentic_kb.security.identifiers")

FIXED_DIALECTS = {"postgres", "mysql", "tsql"}  # sqlglot dialect names


# PostgreSQL reserved words that must be quoted when used as identifiers
RESERVED_WORDS = frozenset(
    """all analyse analyze and any array as asc both case cast check collate column constraint create
    current_date current_time current_timestamp current_user default desc distinct do else end except
    false fetch for foreign from grant group having in initially intersect into leading limit localtime
    localtimestamp not null offset on only or order placing primary references returning select
    session_user some symmetric table then to trailing true union unique user using variadic when
    where window with""".split()
)


def needs_quoting(name: str) -> bool:
    """True if the identifier can't be referenced unquoted in PostgreSQL."""
    plain = name.replace("_", "a").isalnum() and not name[0].isdigit()
    return name != name.lower() or not plain or name.lower() in RESERVED_WORDS


def _unique_spellings(names) -> Dict[str, str]:
    """Map lower-cased name -> exact spelling, dropping names whose spelling is ambiguous."""
    seen: Dict[str, Set[str]] = {}
    for n in names:
        seen.setdefault(n.lower(), set()).add(n)
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


def fix_identifier_case(sql: str, schema: DatabaseSchemaMetadata, dialect: str) -> str:
    """Return `sql` with table/column identifiers matched to the schema's exact spelling.

    Applies to PostgreSQL (case-folding), MySQL (case-sensitive table names on Linux) and SQL Server
    (reserved words such as `user` / `order` need bracket quoting). Returns the input unchanged if it
    can't be parsed (the SQL validator reports syntax errors) or nothing needed fixing.
    """
    glot = sqlglot_dialect(dialect)
    if glot not in FIXED_DIALECTS:
        return sql

    columns = _unique_spellings(c.name for t in schema.tables.values() for c in t.columns)
    tables = _unique_spellings(t.table_name for t in schema.tables.values())

    try:
        tree = sqlglot.parse_one(sql, read=glot)
    except Exception:
        return sql
    if tree is None:
        return sql

    changed = False

    def _fix(ident: exp.Expression, known: Dict[str, str]) -> None:
        nonlocal changed
        if not isinstance(ident, exp.Identifier):
            return
        actual = known.get(ident.name.lower())
        if actual is None:
            return
        want_quoted = needs_quoting(actual)
        if ident.name != actual or bool(ident.args.get("quoted")) != want_quoted:
            ident.set("this", actual)
            ident.set("quoted", want_quoted)
            changed = True

    for col in tree.find_all(exp.Column):
        _fix(col.this, columns)
    for tbl in tree.find_all(exp.Table):
        _fix(tbl.this, tables)

    if not changed:
        return sql
    fixed = tree.sql(dialect=glot)
    logger.info("Normalized identifier case/quoting in generated SQL")
    return fixed
