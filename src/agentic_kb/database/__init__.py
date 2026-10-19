"""Database connectivity and query execution module."""

from agentic_kb.database.base import BaseDatabaseProvider
from agentic_kb.database.factory import DatabaseProviderFactory
from agentic_kb.database.mock import MockDatabaseProvider
from agentic_kb.database.models import (
    ColumnMetadata,
    DatabaseSchemaMetadata,
    QueryResult,
    TableMetadata,
)

__all__ = [
    "BaseDatabaseProvider",
    "PostgreSQLProvider",
    "MySQLProvider",
    "SQLServerProvider",
    "MongoDBProvider",
    "MockDatabaseProvider",
    "DatabaseProviderFactory",
    "ColumnMetadata",
    "TableMetadata",
    "DatabaseSchemaMetadata",
    "QueryResult",
]

_LAZY = {
    "PostgreSQLProvider": "agentic_kb.database.postgres",
    "MySQLProvider": "agentic_kb.database.mysql",
    "SQLServerProvider": "agentic_kb.database.sqlserver",
    "MongoDBProvider": "agentic_kb.database.mongodb",
}


def __getattr__(name: str):
    """Import driver-backed providers on first use so optional drivers stay optional."""
    if name in _LAZY:
        import importlib

        return getattr(importlib.import_module(_LAZY[name]), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
