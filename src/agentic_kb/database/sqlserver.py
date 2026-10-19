"""Microsoft SQL Server database provider powered by SQLAlchemy + pymssql."""

from typing import Any, Dict

from agentic_kb.database.sqlalchemy_base import SQLAlchemyProvider


class SQLServerProvider(SQLAlchemyProvider):
    """
    SQL Server / Azure SQL provider (T-SQL).

    SQL Server has no session-level read-only switch, so read-only access is enforced by the SDK's
    SQL validator and a statement guard; for defence in depth connect with a login that only holds
    the `db_datareader` role. Queries use `TOP n` instead of `LIMIT n`.
    """

    LABEL = "SQL Server"
    SYSTEM_SCHEMAS = {"information_schema", "sys", "guest"}

    @property
    def dialect_name(self) -> str:
        return "sqlserver"

    def _connect_args(self) -> Dict[str, Any]:
        return {
            "login_timeout": int(self.config.connection_timeout_seconds if self.config else 10),
            "timeout": int(self.query_timeout_seconds),  # per-query timeout in seconds
        }

    def _is_connection_error(self, message: str) -> bool:
        return any(
            k in message
            for k in ("unable to connect", "adaptive server connection failed", "login failed", "connection refused")
        )
