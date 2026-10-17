"""Permission and Row-Level Security (RLS) enforcement engine."""

from typing import Dict, List, Optional, Set
import sqlglot
from sqlglot import exp

from agentic_kb.exceptions.errors import PermissionDeniedError
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.security.permissions")


class PermissionEngine:
    """Validates resource permissions and injects Row-Level Security (RLS) predicates."""

    def __init__(
        self,
        allowed_schemas: Optional[List[str]] = None,
        allowed_tables: Optional[List[str]] = None,
        tenant_column: str = "tenant_id",
        user_column: str = "user_id",
        dialect: str = "postgres",
    ):
        self.allowed_schemas = set(s.lower() for s in (allowed_schemas or []))
        self.allowed_tables = set(t.lower() for t in (allowed_tables or []))
        self.tenant_column = tenant_column
        self.user_column = user_column
        self.dialect = dialect

    def check_table_access(self, table_name: str) -> None:
        """Verify access to a specific table."""
        t_clean = table_name.lower().strip()
        if not self.allowed_tables:
            return
        if t_clean not in self.allowed_tables and not any(
            a.endswith(f".{t_clean}") or a == t_clean for a in self.allowed_tables
        ):
            raise PermissionDeniedError(resource=table_name)

    def apply_row_level_security(
        self,
        sql_query: str,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> str:
        """
        Inject multi-tenant and user row-level security predicates into the AST.
        Ensures tenant isolation at the query engine level.
        """
        if not tenant_id and not user_id:
            return sql_query

        try:
            ast = sqlglot.parse_one(sql_query, read=self.dialect)
        except Exception:
            # If parsing fails here, let validator handle syntax error
            return sql_query

        if isinstance(ast, exp.Select):
            predicates: List[str] = []
            if tenant_id:
                predicates.append(f"{self.tenant_column} = '{tenant_id}'")
            if user_id:
                predicates.append(f"{self.user_column} = '{user_id}'")

            for pred in predicates:
                ast = ast.where(pred, copy=False)

            return ast.sql(dialect=self.dialect)

        return sql_query
