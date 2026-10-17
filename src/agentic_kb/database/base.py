"""Base database provider interface."""

import abc
import asyncio
from typing import Any, Dict, List, Optional
from agentic_kb.database.models import DatabaseSchemaMetadata, QueryResult


class BaseDatabaseProvider(abc.ABC):
    """
    Abstract interface for database connectivity, reflection, and safe query execution.

    Supports PostgreSQL, SQL Server, SQLite (for local/testing), and custom enterprise databases.
    """

    def __init__(
        self,
        read_only: bool = True,
        max_rows: int = 1000,
        query_timeout_seconds: float = 30.0,
        **kwargs: Any,
    ):
        self.read_only = read_only
        self.max_rows = max_rows
        self.query_timeout_seconds = query_timeout_seconds
        self.extra_kwargs = kwargs

    @property
    @abc.abstractmethod
    def dialect_name(self) -> str:
        """Database dialect identifier (e.g. 'postgresql', 'sqlite', 'mssql')."""
        pass

    @abc.abstractmethod
    def execute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        max_rows: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> QueryResult:
        """
        Execute a read-only query safely with row limits and timeouts.
        """
        pass

    @abc.abstractmethod
    async def aexecute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        max_rows: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> QueryResult:
        """
        Asynchronously execute a read-only query safely with row limits and timeouts.
        """
        pass

    @abc.abstractmethod
    def get_schema_metadata(
        self,
        allowed_schemas: Optional[List[str]] = None,
        allowed_tables: Optional[List[str]] = None,
    ) -> DatabaseSchemaMetadata:
        """
        Extract catalog metadata (schemas, tables, columns, data types, keys, comments).
        Filters strictly by allowed_schemas and allowed_tables when specified.
        """
        pass

    @abc.abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """
        Execute a lightweight connectivity ping (e.g. SELECT 1) and return status.
        """
        pass

    @abc.abstractmethod
    def close(self) -> None:
        """Dispose connections and release connection pools."""
        pass

    def __enter__(self) -> "BaseDatabaseProvider":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    async def __aenter__(self) -> "BaseDatabaseProvider":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
