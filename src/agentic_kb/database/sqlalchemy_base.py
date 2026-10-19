"""Shared SQLAlchemy-backed provider for relational databases (PostgreSQL, MySQL, SQL Server)."""

import abc
import time
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import create_engine, event, inspect, text
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

logger = get_logger("agentic_kb.database")

# First keywords that are never allowed through a read-only provider
WRITE_VERBS = (
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT", "REVOKE",
    "MERGE", "REPLACE", "EXEC", "EXECUTE", "CALL", "SET", "USE",
)


class SQLAlchemyProvider(BaseDatabaseProvider, abc.ABC):
    """
    Base class for relational providers. Subclasses supply the dialect name, driver connection
    arguments, per-connection session settings (read-only mode, statement timeout) and which
    schemas are system-owned.
    """

    #: Schemas hidden from reflection when no allow-list is configured
    SYSTEM_SCHEMAS: Set[str] = set()
    #: Human name used in error messages
    LABEL = "Database"

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
            raise DatabaseConnectionError(f"{self.LABEL} connection URL or DatabaseConfig must be provided.")

        self.database_name = config.database if config else self.LABEL.lower()
        self.pool_size = config.pool_size if config else pool_size
        self.max_overflow = config.max_overflow if config else max_overflow
        self._engine: Optional[Engine] = None

    # ------------------------------------------------------------------ subclass hooks
    @property
    @abc.abstractmethod
    def dialect_name(self) -> str:
        ...

    def _connect_args(self) -> Dict[str, Any]:
        """Driver-specific connect() arguments (timeouts etc.)."""
        return {}

    def _on_connect(self, dbapi_connection: Any) -> None:
        """Run once per new physical connection: set read-only mode, statement timeout, ..."""

    def _default_schemas(self) -> Optional[List[str]]:
        """Schemas to reflect when the user configured none (None = all non-system schemas)."""
        return None

    def _is_timeout_error(self, message: str) -> bool:
        return "timeout" in message or "timed out" in message

    def _is_connection_error(self, message: str) -> bool:
        return any(k in message for k in ("could not connect", "connection refused", "can't connect"))

    # ------------------------------------------------------------------ engine
    def _get_engine(self) -> Engine:
        if self._engine is None:
            try:
                engine = create_engine(
                    self._url,
                    poolclass=QueuePool,
                    pool_size=self.pool_size,
                    max_overflow=self.max_overflow,
                    pool_pre_ping=True,
                    pool_timeout=self.query_timeout_seconds,
                    connect_args=self._connect_args(),
                )
                event.listen(engine, "connect", lambda dbapi_conn, _record: self._on_connect(dbapi_conn))
                self._engine = engine
            except Exception as e:
                raise DatabaseConnectionError(
                    f"Failed to create {self.LABEL} engine: {str(e)}",
                    details={"url": self._url.split("@")[-1]},
                ) from e
        return self._engine

    # ------------------------------------------------------------------ execution
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

        if self.read_only:
            first_word = query.strip().split(None, 1)[0].upper() if query.strip() else ""
            if first_word in WRITE_VERBS:
                raise SecurityError(
                    "Read-only policy violation: data-modifying or DDL statements are blocked."
                )

        start_time = time.time()
        try:
            with engine.connect() as conn:
                # Without bind params the SQL goes straight to the driver, so literals such as
                # '10:30' are never mistaken for :named bind parameters. The DBAPI drivers use
                # %-style placeholders, so literal percent signs (LIKE '%x%') must be doubled.
                if params:
                    cursor_result = conn.execute(text(query), params)
                else:
                    sql = query.replace("%", "%%") if engine.dialect.paramstyle in ("format", "pyformat") else query
                    cursor_result = conn.exec_driver_sql(sql)

                columns = list(cursor_result.keys()) if cursor_result.returns_rows else []
                raw_rows = cursor_result.fetchmany(limit + 1) if cursor_result.returns_rows else []
                duration_ms = round((time.time() - start_time) * 1000, 2)

                is_truncated = len(raw_rows) > limit
                if is_truncated:
                    raw_rows = raw_rows[:limit]
                rows = [dict(row._mapping) for row in raw_rows]

                return QueryResult(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    duration_ms=duration_ms,
                    is_truncated=is_truncated,
                    query=query,
                )
        except SecurityError:
            raise
        except Exception as e:
            err_msg = str(e).lower()
            if self._is_timeout_error(err_msg):
                raise DatabaseTimeoutError(timeout_seconds=timeout) from e
            if self._is_connection_error(err_msg):
                raise DatabaseConnectionError(f"Database unavailable: {str(e)}") from e
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

    # ------------------------------------------------------------------ reflection
    def get_schema_metadata(
        self,
        allowed_schemas: Optional[List[str]] = None,
        allowed_tables: Optional[List[str]] = None,
    ) -> DatabaseSchemaMetadata:
        """Inspect and reflect the database catalog (tables, views, columns, keys, comments)."""
        engine = self._get_engine()
        try:
            inspector = inspect(engine)
            all_schemas = inspector.get_schema_names()
        except Exception as e:
            raise DatabaseConnectionError(f"Failed to inspect database: {str(e)}") from e

        wanted = allowed_schemas or self._default_schemas()
        if wanted:
            lowered = {s.lower() for s in wanted}
            target_schemas = [s for s in all_schemas if s.lower() in lowered]
        else:
            target_schemas = [
                s for s in all_schemas
                if s.lower() not in self.SYSTEM_SCHEMAS and not s.lower().startswith("db_")
            ]

        allowed_lower = {t.lower() for t in (allowed_tables or [])}
        tables_meta: Dict[str, TableMetadata] = {}

        for schema in target_schemas:
            try:
                all_tbls = inspector.get_table_names(schema=schema) + inspector.get_view_names(schema=schema)
            except Exception as e:
                logger.warning(f"Could not list tables for schema '{schema}': {str(e)}")
                continue

            for tbl in all_tbls:
                full_name = f"{schema}.{tbl}"
                if allowed_lower and full_name.lower() not in allowed_lower and tbl.lower() not in allowed_lower:
                    continue

                try:
                    columns_info = inspector.get_columns(tbl, schema=schema)
                    pk_constraint = inspector.get_pk_constraint(tbl, schema=schema)
                    pks = pk_constraint.get("constrained_columns", []) if pk_constraint else []
                    fks = inspector.get_foreign_keys(tbl, schema=schema)
                    indexes = [idx.get("name", "") for idx in inspector.get_indexes(tbl, schema=schema)]
                    try:
                        comment = inspector.get_table_comment(tbl, schema=schema).get("text")
                    except NotImplementedError:
                        comment = None
                except Exception as e:
                    logger.warning(f"Failed to reflect table '{full_name}': {str(e)}")
                    continue

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
                    fk_info = fk_map.get(cname)
                    cols.append(
                        ColumnMetadata(
                            name=cname,
                            data_type=str(col.get("type", "")),
                            is_nullable=bool(col.get("nullable", True)),
                            is_primary_key=cname in pks,
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
        """Quick connectivity ping."""
        start = time.time()
        try:
            self.execute("SELECT 1 AS ping", timeout_seconds=5.0)
            return {
                "status": "healthy",
                "dialect": self.dialect_name,
                "database": self.database_name,
                "latency_ms": round((time.time() - start) * 1000, 2),
                "connection": "ok",
            }
        except Exception as e:
            return {"status": "unhealthy", "dialect": self.dialect_name, "error": str(e)}

    def close(self) -> None:
        """Dispose the SQLAlchemy engine and pool."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
