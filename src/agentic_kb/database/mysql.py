"""MySQL / MariaDB database provider powered by SQLAlchemy + PyMySQL."""

from typing import Any, Dict, List, Optional

from agentic_kb.database.sqlalchemy_base import SQLAlchemyProvider
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.database.mysql")


class MySQLProvider(SQLAlchemyProvider):
    """
    MySQL / MariaDB provider.

    In MySQL a "schema" is a database, so reflection defaults to the configured database and tables
    are addressed as `database.table`. Sessions are opened read-only with a server-side
    statement time limit where the server supports it (MySQL 5.7.8+; MariaDB uses max_statement_time).
    """

    LABEL = "MySQL"
    SYSTEM_SCHEMAS = {"information_schema", "mysql", "performance_schema", "sys"}

    @property
    def dialect_name(self) -> str:
        return "mysql"

    def _connect_args(self) -> Dict[str, Any]:
        timeout = int(self.config.connection_timeout_seconds if self.config else 10)
        return {
            "connect_timeout": timeout,
            "read_timeout": int(self.query_timeout_seconds) + 5,  # socket backstop behind the server limit
            "write_timeout": int(self.query_timeout_seconds) + 5,
        }

    def _on_connect(self, dbapi_connection: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            if self.read_only:
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
            ms = int(self.query_timeout_seconds * 1000)
            for statement in (
                f"SET SESSION MAX_EXECUTION_TIME={ms}",        # MySQL
                f"SET SESSION max_statement_time={ms / 1000}",  # MariaDB
            ):
                try:
                    cursor.execute(statement)
                    break
                except Exception:
                    continue
        finally:
            cursor.close()

    def _default_schemas(self) -> Optional[List[str]]:
        return [self.config.database] if self.config and self.config.database else None

    def _is_timeout_error(self, message: str) -> bool:
        return (
            "timeout" in message
            or "timed out" in message
            or "maximum statement execution time exceeded" in message
            or "max_statement_time" in message
        )

    def _is_connection_error(self, message: str) -> bool:
        return any(
            k in message for k in ("can't connect", "connection refused", "lost connection", "2003", "2013")
        )
