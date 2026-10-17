"""PostgreSQL database provider powered by SQLAlchemy."""

import time
from typing import Any, Dict, List, Optional
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

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
    QueryExecutionError,
    SecurityError,
)
from agentic_kb.models.config import DatabaseConfig
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.database.postgres")


class PostgreSQLProvider(BaseDatabaseProvider):
    """
    Production-ready PostgreSQL database provider.

    Enforces connection pooling, statement timeouts, read-only connections,
    and automatic metadata extraction via SQLAlchemy reflection.
    """

    def __init__(
        self,
        config: Optional[DatabaseConfig] = None,
        connection_url: Optional[str] = None,
        read_only: bool = True,
        max_rows: int = 1000,
        query_timeout_seconds: float = 30.0,
        pool_size: int = 5,
        max_overflow: int = 10,
        **kwargs: Any,
    ):
        super().__init__(
            read_only=read_only,
            max_rows=max_rows,
            query_timeout_seconds=query_timeout_seconds,
            **kwargs,
        )
        self.config = config
        self._url = connection_url or (config.get_connection_url() if config else None)
        if not self._url:
            raise DatabaseConnectionError("PostgreSQL connection URL or DatabaseConfig must be provided.")

        self.database_name = config.database if config else "postgres"
        self.pool_size = config.pool_size if config else pool_size
        self.max_overflow = config.max_overflow if config else max_overflow
        self._engine: Optional[Engine] = None

    @property
    def dialect_name(self) -> str:
        return "postgresql"

    def _get_engine(self) -> Engine:
        if self._engine is None:
            connect_args: Dict[str, Any] = {
                "connect_timeout": int(self.config.connection_timeout_seconds if self.config else 10),
            }
            # If postgres dialect, pass statement timeout to connect_args
            timeout_ms = int(self.query_timeout_seconds * 1000)
            connect_args["options"] = f"-c statement_timeout={timeout_ms}"

            try:
                self._engine = create_engine(
                    self._url,
                    poolclass=QueuePool,
                    pool_size=self.pool_size,
                    max_overflow=self.max_overflow,
                    pool_pre_ping=True,
                    pool_timeout=self.query_timeout_seconds,
                    connect_args=connect_args,
                    execution_options={"readonly": self.read_only} if self.read_only else {},
                )
            except Exception as e:
                raise DatabaseConnectionError(
                    f"Failed to create PostgreSQL engine: {str(e)}",
                    details={"url": self._url.split("@")[-1]},
                ) from e
        return self._engine

    def execute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        max_rows: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> QueryResult:
        engine = self._get_engine()
        limit = max_rows or self.max_rows
        timeout = timeout_seconds or self.query_timeout_seconds

        # Guard against DML/DDL when read_only is enabled
        upper_query = query.strip().upper()
        if self.read_only:
            forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT", "REVOKE"]
            if any(upper_query.startswith(verb) for verb in forbidden):
                raise SecurityError(
                    "Read-only policy violation: data-modifying or DDL statements are blocked."
                )

        start_time = time.time()
        try:
            with engine.connect() as conn:
                # Set transaction to read only where supported
                if self.read_only:
                    conn = conn.execution_options(readonly=True)

                stmt = text(query)
                cursor_result = conn.execute(stmt, params or {})

                columns = list(cursor_result.keys()) if cursor_result.returns_rows else []
                raw_rows = cursor_result.fetchmany(limit + 1) if cursor_result.returns_rows else []
                duration_ms = round((time.time() - start_time) * 1000, 2)

                is_truncated = len(raw_rows) > limit
                if is_truncated:
                    raw_rows = raw_rows[:limit]

                # Convert Row mappings to dicts
                rows = [dict(row._mapping) for row in raw_rows]

                return QueryResult(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    duration_ms=duration_ms,
                    is_truncated=is_truncated,
                    query=query,
                )
        except Exception as e:
            err_msg = str(e).lower()
            if "timeout" in err_msg or "canceling statement due to statement timeout" in err_msg:
                raise DatabaseTimeoutError(timeout_seconds=timeout) from e
            if "could not connect" in err_msg or "connection refused" in err_msg:
                raise DatabaseConnectionError(f"Database unavailable: {str(e)}") from e
            if isinstance(e, SecurityError):
                raise
            raise QueryExecutionError(f"Query execution error: {str(e)}") from e

    async def aexecute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        max_rows: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> QueryResult:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.execute(query, params=params, max_rows=max_rows, timeout_seconds=timeout_seconds),
        )

    def get_schema_metadata(
        self,
        allowed_schemas: Optional[List[str]] = None,
        allowed_tables: Optional[List[str]] = None,
    ) -> DatabaseSchemaMetadata:
        """Inspect and reflect database schema catalog."""
        engine = self._get_engine()
        try:
            inspector = inspect(engine)
        except Exception as e:
            raise DatabaseConnectionError(f"Failed to inspect database: {str(e)}") from e

        all_schemas = inspector.get_schema_names()
        target_schemas = (
            [s for s in all_schemas if s in allowed_schemas]
            if allowed_schemas
            else [s for s in all_schemas if s not in ("pg_catalog", "information_schema", "pg_toast")]
        )

        tables_meta: Dict[str, TableMetadata] = {}

        for schema in target_schemas:
            try:
                table_names = inspector.get_table_names(schema=schema)
                # Also include views
                view_names = inspector.get_view_names(schema=schema)
                all_tbls = table_names + view_names
            except Exception as e:
                logger.warning(f"Could not list tables for schema '{schema}': {str(e)}")
                continue

            for tbl in all_tbls:
                full_name = f"{schema}.{tbl}"
                # Check table allowlist if configured
                if allowed_tables and full_name not in allowed_tables and tbl not in allowed_tables:
                    continue

                try:
                    columns_info = inspector.get_columns(tbl, schema=schema)
                    pk_constraint = inspector.get_pk_constraint(tbl, schema=schema)
                    pks = pk_constraint.get("constrained_columns", []) if pk_constraint else []
                    fks = inspector.get_foreign_keys(tbl, schema=schema)
                    indexes = [idx.get("name", "") for idx in inspector.get_indexes(tbl, schema=schema)]
                    comment = inspector.get_table_comment(tbl, schema=schema).get("text")
                except Exception as e:
                    logger.warning(f"Failed to reflect table '{full_name}': {str(e)}")
                    continue

                # Build foreign key mapping by column name
                fk_map: Dict[str, Dict[str, str]] = {}
                for fk in fks:
                    referred_table = fk.get("referred_table")
                    referred_schema = fk.get("referred_schema") or schema
                    ref_full = f"{referred_schema}.{referred_table}" if referred_schema else referred_table
                    for col, ref_col in zip(fk.get("constrained_columns", []), fk.get("referred_columns", [])):
                        fk_map[col] = {"table": ref_full, "column": ref_col}

                cols: List[ColumnMetadata] = []
                for col in columns_info:
                    cname = col.get("name", "")
                    is_pk = cname in pks
                    fk_info = fk_map.get(cname)
                    cols.append(
                        ColumnMetadata(
                            name=cname,
                            data_type=str(col.get("type", "")),
                            is_nullable=bool(col.get("nullable", True)),
                            is_primary_key=is_pk,
                            is_foreign_key=bool(fk_info),
                            foreign_table=fk_info.get("table") if fk_info else None,
                            foreign_column=fk_info.get("column") if fk_info else None,
                            description=col.get("comment"),
                            default_value=str(col.get("default")) if col.get("default") is not None else None,
                        )
                    )

                tables_meta[full_name] = TableMetadata(
                    schema_name=schema,
                    table_name=tbl,
                    full_name=full_name,
                    columns=cols,
                    primary_keys=pks,
                    foreign_keys=fks,
                    indexes=indexes,
                    description=comment,
                )

        return DatabaseSchemaMetadata(
            dialect=self.dialect_name,
            database_name=self.database_name,
            tables=tables_meta,
        )

    def health_check(self) -> Dict[str, Any]:
        """Perform a quick database connection health check."""
        start = time.time()
        try:
            res = self.execute("SELECT 1 AS ping", timeout_seconds=5.0)
            duration_ms = round((time.time() - start) * 1000, 2)
            return {
                "status": "healthy",
                "dialect": self.dialect_name,
                "database": self.database_name,
                "latency_ms": duration_ms,
                "connection": "ok",
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "dialect": self.dialect_name,
                "error": str(e),
            }

    def close(self) -> None:
        """Dispose the SQLAlchemy engine and pool."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
