"""Microsoft SQL Server database provider powered by SQLAlchemy + pymssql/pyodbc."""

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

logger = get_logger("agentic_kb.database.sqlserver")

# DML/DDL verbs to block when read_only is enabled
_WRITE_VERBS = frozenset([
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
    "CREATE", "TRUNCATE", "GRANT", "REVOKE", "EXEC", "EXECUTE",
])

# SQL Server system schemas to skip during reflection
_SYSTEM_SCHEMAS = frozenset([
    "sys", "INFORMATION_SCHEMA", "db_owner", "db_accessadmin",
    "db_securityadmin", "db_ddladmin", "db_backupoperator",
    "db_datareader", "db_datawriter", "db_denydatareader", "db_denydatawriter",
    "guest",
])


class SQLServerProvider(BaseDatabaseProvider):
    """
    Production-ready Microsoft SQL Server database provider.

    Enforces connection pooling, lock timeouts, read-only statement
    validation, and automatic metadata extraction via SQLAlchemy reflection.

    Supports:
    - pymssql driver (default, lightweight): mssql+pymssql
    - pyodbc driver (Windows ODBC): mssql+pyodbc

    Example usage::

        from agentic_kb.database.sqlserver import SQLServerProvider
        from agentic_kb.models.config import DatabaseConfig

        cfg = DatabaseConfig(
            type="sqlserver",
            host="my-sql-server.example.com",
            port=1433,
            database="SalesDB",
            username="sa",
            password_env="MSSQL_PASSWORD",
        )
        provider = SQLServerProvider(config=cfg)
        result = provider.execute("SELECT TOP 10 * FROM dbo.Orders")
    """

    def __init__(
        self,
        config: Optional[DatabaseConfig] = None,
        connection_url: Optional[str] = None,
        driver: str = "pymssql",
        read_only: bool = True,
        max_rows: int = 1000,
        query_timeout_seconds: float = 30.0,
        pool_size: int = 5,
        max_overflow: int = 10,
        **kwargs: Any,
    ):
        """
        Args:
            config: DatabaseConfig instance (preferred).
            connection_url: Raw SQLAlchemy URL (overrides config URL).
            driver: SQL Server driver -- 'pymssql' or 'pyodbc'.
            read_only: Block all write/DDL statements.
            max_rows: Maximum rows returned per query.
            query_timeout_seconds: Per-statement timeout in seconds.
            pool_size: Connection pool baseline size.
            max_overflow: Extra connections beyond pool_size.
        """
        super().__init__(
            read_only=read_only,
            max_rows=max_rows,
            query_timeout_seconds=query_timeout_seconds,
            **kwargs,
        )
        self.config = config
        self.driver = driver
        self._url = connection_url or self._build_url(config, driver)
        if not self._url:
            raise DatabaseConnectionError(
                "SQL Server connection URL or DatabaseConfig must be provided."
            )

        self.database_name = config.database if config else "master"
        self.pool_size = config.pool_size if config else pool_size
        self.max_overflow = config.max_overflow if config else max_overflow
        self._engine: Optional[Engine] = None

    @staticmethod
    def _parse_host_instance(host: str) -> tuple[str, Optional[str]]:
        """
        Split 'SERVER\\INSTANCE' or 'SERVER/INSTANCE' into (server, instance).
        Returns (host, None) if no named instance is present.
        """
        for sep in ("\\", "/"):
            if sep in host:
                parts = host.split(sep, 1)
                return parts[0].strip(), parts[1].strip()
        return host.strip(), None

    @staticmethod
    def _build_odbc_connection_string(config: DatabaseConfig, driver_name: str = "ODBC Driver 17 for SQL Server") -> str:
        """
        Build an ODBC connection string that correctly handles:
        - Named instances (SERVER\\INSTANCE)
        - Windows Authentication (Trusted_Connection=yes)
        - SQL Server Authentication (username + password)
        """
        parts = [
            f"DRIVER={{{driver_name}}}",
            f"SERVER={config.host}",      # full SERVER\INSTANCE passed as-is
            f"DATABASE={config.database}",
        ]
        pwd = config.get_password() or ""
        if config.username and pwd:
            parts.append(f"UID={config.username}")
            parts.append(f"PWD={pwd}")
        else:
            # Windows Authentication
            parts.append("Trusted_Connection=yes")
        return ";".join(parts) + ";"

    @staticmethod
    def _build_url(config: Optional[DatabaseConfig], driver: str) -> Optional[str]:
        """
        Build the SQLAlchemy connection URL.

        For pyodbc with named instances, we return a minimal placeholder URL
        and rely on the `creator` callable in _get_engine() for the real connection.
        For pymssql, we strip the instance from the URL host.
        """
        if not config:
            return None
        if driver == "pyodbc":
            # URL is only used to identify the dialect; real connection is via creator()
            server_host, _ = SQLServerProvider._parse_host_instance(config.host)
            return f"mssql+pyodbc://{server_host}/{config.database}?odbc_connect=placeholder"
        # pymssql fallback
        pwd = config.get_password() or ""
        pwd_part = f":{pwd}" if pwd else ""
        user_pwd = f"{config.username}{pwd_part}"
        server_host, _ = SQLServerProvider._parse_host_instance(config.host)
        return f"mssql+pymssql://{user_pwd}@{server_host}:{config.port}/{config.database}"

    @property
    def dialect_name(self) -> str:
        return "tsql"

    def _get_engine(self) -> Engine:
        """Lazily create the SQLAlchemy engine with connection pool."""
        if self._engine is None:
            timeout_secs = int(self.query_timeout_seconds)

            if self.driver == "pyodbc" and self.config:
                # Build real connection via ODBC connection string creator.
                # This is the reliable path for named instances + Windows Auth.
                import pyodbc
                odbc_str = self._build_odbc_connection_string(self.config)

                def _creator():
                    return pyodbc.connect(odbc_str, timeout=timeout_secs)

                try:
                    self._engine = create_engine(
                        "mssql+pyodbc://",
                        creator=_creator,
                        poolclass=QueuePool,
                        pool_size=self.pool_size,
                        max_overflow=self.max_overflow,
                        pool_pre_ping=True,
                        pool_timeout=self.query_timeout_seconds,
                    )
                except Exception as e:
                    raise DatabaseConnectionError(
                        f"Failed to create SQL Server engine (pyodbc): {str(e)}",
                        details={"database": self.database_name, "server": self.config.host},
                    ) from e
            else:
                # pymssql fallback
                connect_args: Dict[str, Any] = {
                    "timeout": timeout_secs,
                    "login_timeout": int(
                        self.config.connection_timeout_seconds if self.config else 10
                    ),
                }
                try:
                    self._engine = create_engine(
                        self._url,
                        poolclass=QueuePool,
                        pool_size=self.pool_size,
                        max_overflow=self.max_overflow,
                        pool_pre_ping=True,
                        pool_timeout=self.query_timeout_seconds,
                        connect_args=connect_args,
                    )
                except Exception as e:
                    raise DatabaseConnectionError(
                        f"Failed to create SQL Server engine (pymssql): {str(e)}",
                        details={"database": self.database_name},
                    ) from e

            logger.info(
                "SQL Server engine created",
                extra={
                    "server": self.config.host if self.config else "unknown",
                    "database": self.database_name,
                    "driver": self.driver,
                },
            )
        return self._engine

    def _enforce_read_only(self, query: str) -> None:
        """Raise SecurityError if query contains write/DDL verbs."""
        if not self.read_only:
            return
        stripped = query.strip()
        first_token = stripped.split()[0].upper() if stripped.split() else ""
        if first_token in _WRITE_VERBS:
            raise SecurityError(
                f"Read-only policy violation: '{first_token}' statements are blocked. "
                "Set read_only=False or use a write-enabled database connection."
            )

    def execute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        max_rows: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> QueryResult:
        """
        Execute a T-SQL query safely with row limits and read-only enforcement.

        Args:
            query: T-SQL query string.
            params: Named bind parameters dict.
            max_rows: Override default max row limit.
            timeout_seconds: Override default query timeout.

        Returns:
            QueryResult with columns, rows, duration, and truncation flag.
        """
        self._enforce_read_only(query)
        engine = self._get_engine()
        limit = max_rows or self.max_rows
        timeout = timeout_seconds or self.query_timeout_seconds

        start_time = time.time()
        try:
            with engine.connect() as conn:
                # SQL Server LOCK_TIMEOUT in milliseconds (-1 = wait forever)
                lock_timeout_ms = int(timeout * 1000)
                conn.execute(text(f"SET LOCK_TIMEOUT {lock_timeout_ms}"))

                stmt = text(query)
                cursor_result = conn.execute(stmt, params or {})

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
            if "timeout" in err_msg or "lock timeout" in err_msg or "query timeout" in err_msg:
                raise DatabaseTimeoutError(timeout_seconds=timeout) from e
            if "login failed" in err_msg or "cannot open database" in err_msg or "tcp provider" in err_msg:
                raise DatabaseConnectionError(f"SQL Server connection failed: {str(e)}") from e
            raise QueryExecutionError(f"Query execution error: {str(e)}") from e

    async def aexecute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        max_rows: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> QueryResult:
        """Async wrapper around execute() using a thread executor."""
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
        """
        Reflect and return schema/table/column metadata for the SQL Server database.

        Skips system schemas. Respects allowed_schemas and allowed_tables allowlists.
        """
        engine = self._get_engine()
        try:
            inspector = inspect(engine)
        except Exception as e:
            raise DatabaseConnectionError(f"Failed to inspect SQL Server database: {str(e)}") from e

        all_schemas = inspector.get_schema_names()
        target_schemas = (
            [s for s in all_schemas if s in allowed_schemas]
            if allowed_schemas
            else [s for s in all_schemas if s not in _SYSTEM_SCHEMAS]
        )

        tables_meta: Dict[str, TableMetadata] = {}

        for schema in target_schemas:
            try:
                table_names = inspector.get_table_names(schema=schema)
                view_names = inspector.get_view_names(schema=schema)
                all_tbls = table_names + view_names
            except Exception as e:
                logger.warning(f"Could not list tables for schema '{schema}': {str(e)}")
                continue

            for tbl in all_tbls:
                full_name = f"{schema}.{tbl}"
                if allowed_tables and full_name not in allowed_tables and tbl not in allowed_tables:
                    continue

                try:
                    columns_info = inspector.get_columns(tbl, schema=schema)
                    pk_constraint = inspector.get_pk_constraint(tbl, schema=schema)
                    pks = pk_constraint.get("constrained_columns", []) if pk_constraint else []
                    fks = inspector.get_foreign_keys(tbl, schema=schema)
                    indexes = [idx.get("name", "") for idx in inspector.get_indexes(tbl, schema=schema)]
                    try:
                        comment = inspector.get_table_comment(tbl, schema=schema).get("text")
                    except Exception:
                        comment = None
                except Exception as e:
                    logger.warning(f"Failed to reflect table '{full_name}': {str(e)}")
                    continue

                # Build FK column map
                fk_map: Dict[str, Dict[str, str]] = {}
                for fk in fks:
                    referred_table = fk.get("referred_table")
                    referred_schema = fk.get("referred_schema") or schema
                    ref_full = (
                        f"{referred_schema}.{referred_table}" if referred_schema else referred_table
                    )
                    for col, ref_col in zip(
                        fk.get("constrained_columns", []), fk.get("referred_columns", [])
                    ):
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
                            default_value=(
                                str(col.get("default")) if col.get("default") is not None else None
                            ),
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
        """Perform a lightweight SQL Server connectivity ping."""
        start = time.time()
        try:
            self.execute("SELECT 1 AS ping", timeout_seconds=5.0)
            duration_ms = round((time.time() - start) * 1000, 2)
            return {
                "status": "healthy",
                "dialect": self.dialect_name,
                "database": self.database_name,
                "latency_ms": duration_ms,
                "connection": "ok",
                "driver": self.driver,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "dialect": self.dialect_name,
                "database": self.database_name,
                "error": str(e),
                "driver": self.driver,
            }

    def close(self) -> None:
        """Dispose the SQLAlchemy engine and its connection pool."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
            logger.info("SQL Server engine disposed", extra={"database": self.database_name})
