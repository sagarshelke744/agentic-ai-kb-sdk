"""Mock and In-Memory SQLite Database Provider for testing and local development."""

import sqlite3
import time
from typing import Any, Dict, List, Optional
from agentic_kb.database.base import BaseDatabaseProvider
from agentic_kb.database.models import (
    ColumnMetadata,
    DatabaseSchemaMetadata,
    QueryResult,
    TableMetadata,
)
from agentic_kb.exceptions.errors import (
    DatabaseConnectionError,
    DatabaseTimeoutError,
    PermissionDeniedError,
    QueryExecutionError,
    SecurityError,
)
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.database.mock")


class MockDatabaseProvider(BaseDatabaseProvider):
    """
    In-memory database provider built on standard library sqlite3.
    Requires no external database services. Perfect for fast unit testing,
    CI/CD, and local prototyping.
    """

    def __init__(
        self,
        database_name: str = "mock_db",
        initial_tables: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        table_descriptions: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.database_name = database_name
        self.table_descriptions = table_descriptions or {}
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._closed = False

        if initial_tables:
            for table_name, rows in initial_tables.items():
                self._populate_table(table_name, rows)

    @property
    def dialect_name(self) -> str:
        return "sqlite"

    def _populate_table(self, table_name: str, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        columns = list(rows[0].keys())
        col_defs = ", ".join([f'"{c}" TEXT' for c in columns])
        # Clean table name for safe SQLite identifier
        clean_name = table_name.replace(".", "_")
        self._conn.execute(f'CREATE TABLE IF NOT EXISTS "{clean_name}" ({col_defs})')
        placeholders = ", ".join(["?"] * len(columns))
        sql = f'INSERT INTO "{clean_name}" ({", ".join([f"{c}" for c in columns])}) VALUES ({placeholders})'
        for row in rows:
            values = [str(row.get(c, "")) for c in columns]
            self._conn.execute(sql, values)
        self._conn.commit()

    def execute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        max_rows: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> QueryResult:
        if self._closed:
            raise DatabaseConnectionError("Mock database connection is closed.")

        limit = max_rows or self.max_rows
        timeout = timeout_seconds or self.query_timeout_seconds

        # Read-only guard: prevent write statements in query
        upper_query = query.strip().upper()
        if self.read_only:
            forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"]
            if any(upper_query.startswith(verb) for verb in forbidden):
                raise SecurityError(
                    f"Read-only violation: DML/DDL statement blocked in database engine."
                )

        start_time = time.time()
        try:
            cursor = self._conn.cursor()
            cursor.execute(query, params or {})
            rows_raw = cursor.fetchmany(limit + 1)
            duration_ms = round((time.time() - start_time) * 1000, 2)

            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            is_truncated = len(rows_raw) > limit
            if is_truncated:
                rows_raw = rows_raw[:limit]

            rows = [dict(r) for r in rows_raw]
            return QueryResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                duration_ms=duration_ms,
                is_truncated=is_truncated,
                query=query,
            )
        except Exception as e:
            if isinstance(e, SecurityError):
                raise
            raise QueryExecutionError(f"Database query execution failed: {str(e)}") from e

    async def aexecute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        max_rows: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> QueryResult:
        # Standard synchronous execution in in-memory SQLite
        return self.execute(query, params=params, max_rows=max_rows, timeout_seconds=timeout_seconds)

    def get_schema_metadata(
        self,
        allowed_schemas: Optional[List[str]] = None,
        allowed_tables: Optional[List[str]] = None,
    ) -> DatabaseSchemaMetadata:
        if self._closed:
            raise DatabaseConnectionError("Mock database connection is closed.")

        cursor = self._conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables_meta: Dict[str, TableMetadata] = {}

        for (table_name,) in cursor.fetchall():
            # Check allowed tables filter if provided
            if allowed_tables:
                # Table name may be schema.table or flat table
                if table_name not in allowed_tables and not any(
                    t.endswith(f".{table_name}") or t.replace(".", "_") == table_name
                    for t in allowed_tables
                ):
                    continue

            # Inspect columns
            pragma_cursor = self._conn.cursor()
            pragma_cursor.execute(f'PRAGMA table_info("{table_name}");')
            cols: List[ColumnMetadata] = []
            pks: List[str] = []

            for row in pragma_cursor.fetchall():
                # row: (cid, name, type, notnull, dflt_value, pk)
                col_name = row[1]
                data_type = row[2] or "TEXT"
                is_not_null = bool(row[3])
                default_val = str(row[4]) if row[4] is not None else None
                is_pk = bool(row[5])

                if is_pk:
                    pks.append(col_name)

                cols.append(
                    ColumnMetadata(
                        name=col_name,
                        data_type=data_type,
                        is_nullable=not is_not_null,
                        is_primary_key=is_pk,
                        default_value=default_val,
                    )
                )

            desc = self.table_descriptions.get(table_name)
            tables_meta[table_name] = TableMetadata(
                schema_name="main",
                table_name=table_name,
                full_name=table_name,
                columns=cols,
                primary_keys=pks,
                description=desc,
            )

        return DatabaseSchemaMetadata(
            dialect=self.dialect_name,
            database_name=self.database_name,
            tables=tables_meta,
        )

    def health_check(self) -> Dict[str, Any]:
        if self._closed:
            return {"status": "error", "error": "Database closed"}
        try:
            self._conn.execute("SELECT 1").fetchone()
            return {
                "status": "healthy",
                "dialect": self.dialect_name,
                "database": self.database_name,
                "connection": "ok",
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def close(self) -> None:
        if not self._closed:
            self._conn.close()
            self._closed = True
