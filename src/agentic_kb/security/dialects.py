"""Mapping between SDK database dialect names and sqlglot dialect names."""

_SQLGLOT_NAMES = {
    "postgresql": "postgres",
    "postgres": "postgres",
    "mysql": "mysql",
    "mariadb": "mysql",
    "sqlserver": "tsql",
    "mssql": "tsql",
    "tsql": "tsql",
    "sqlite": "sqlite",
}


def sqlglot_dialect(name: str) -> str:
    """Return the sqlglot dialect for an SDK dialect name (unknown names pass through lower-cased)."""
    key = (name or "").lower()
    return _SQLGLOT_NAMES.get(key, key)
