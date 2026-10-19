"""PostgreSQL database provider powered by SQLAlchemy."""

from typing import Any, Dict

from agentic_kb.database.sqlalchemy_base import SQLAlchemyProvider


class PostgreSQLProvider(SQLAlchemyProvider):
    """
    Production-ready PostgreSQL provider.

    Enforces connection pooling, a server-side statement timeout and (when read_only) a
    read-only session via `default_transaction_read_only`, plus automatic metadata reflection.
    """

    LABEL = "PostgreSQL"
    SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}

    @property
    def dialect_name(self) -> str:
        return "postgresql"

    def _connect_args(self) -> Dict[str, Any]:
        timeout_ms = int(self.query_timeout_seconds * 1000)
        options = f"-c statement_timeout={timeout_ms}"
        if self.read_only:
            options += " -c default_transaction_read_only=on"
        return {
            "connect_timeout": int(self.config.connection_timeout_seconds if self.config else 10),
            "options": options,
        }

    def _is_timeout_error(self, message: str) -> bool:
        return "timeout" in message or "canceling statement due to statement timeout" in message
