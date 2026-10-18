"""AST-based SQL Security Validator using sqlglot."""

import re
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field
import sqlglot
from sqlglot import exp

from agentic_kb.exceptions.errors import SQLValidationError
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.security.sql_validator")


class SQLValidationResult(BaseModel):
    """Result of SQL security and syntax validation."""

    is_valid: bool = Field(..., description="Whether SQL passed all security checks")
    cleaned_sql: str = Field(default="", description="Sanitized, normalized SQL with enforced limits")
    tables_used: List[str] = Field(default_factory=list, description="Tables referenced in the query")
    columns_used: List[str] = Field(default_factory=list, description="Columns referenced in the query")
    operations: List[str] = Field(default_factory=list, description="SQL operations detected (e.g. SELECT)")
    errors: List[str] = Field(default_factory=list, description="Validation failure messages")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings")


class SQLValidator:
    """
    Production-grade SQL Validator.

    Enforces:
    1. Single statement execution (blocks SQL injection statement chaining)
    2. Read-only operation allowlist (SELECT and WITH only; blocks INSERT/UPDATE/DELETE/DDL)
    3. Schema & Table allowlist validation
    4. Optional Column-level allowlist validation
    5. Automatic LIMIT clause injection / capping
    6. Query complexity limits (max joins)
    """

    FORBIDDEN_EXPRESSION_TYPES = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Alter,
        exp.Create,
        exp.Command,
        exp.TruncateTable,
        exp.Pragma,
    )

    def __init__(
        self,
        allowed_schemas: Optional[List[str]] = None,
        allowed_tables: Optional[List[str]] = None,
        allowed_columns: Optional[Dict[str, List[str]]] = None,
        read_only: bool = True,
        max_rows: int = 1000,
        enforce_limit: bool = True,
        max_joins: int = 10,
        dialect: str = "postgres",
    ):
        self.allowed_schemas = set(s.lower() for s in (allowed_schemas or []))
        self.allowed_tables = set(t.lower() for t in (allowed_tables or []))
        # Format allowed_columns: table_name (lower) -> set of column names (lower)
        self.allowed_columns: Optional[Dict[str, Set[str]]] = None
        if allowed_columns:
            self.allowed_columns = {
                t.lower(): set(c.lower() for c in cols)
                for t, cols in allowed_columns.items()
            }
        self.read_only = read_only
        self.max_rows = max_rows
        self.enforce_limit = enforce_limit
        self.max_joins = max_joins
        # Map SDK dialect names to sqlglot dialect names
        self.dialect = {"postgresql": "postgres", "sqlserver": "tsql", "mssql": "tsql"}.get(
            dialect.lower(), dialect.lower()
        )

    def validate(self, sql_query: str) -> SQLValidationResult:
        """Parse and validate SQL query against security boundaries."""
        clean_input = sql_query.strip()
        # Remove trailing semicolons
        clean_input = re.sub(r";+\s*$", "", clean_input).strip()

        errors: List[str] = []
        warnings: List[str] = []

        if not clean_input:
            return SQLValidationResult(
                is_valid=False,
                errors=["Query is empty."],
            )

        # 1. Multi-statement injection check
        # Check if multiple statements were combined with semicolon
        try:
            parsed_expressions = sqlglot.parse(clean_input, read=self.dialect)
        except Exception as e:
            return SQLValidationResult(
                is_valid=False,
                errors=[f"SQL Syntax Error: {str(e)}"],
            )

        # Filter out empty statements
        parsed_expressions = [p for p in parsed_expressions if p is not None]

        if len(parsed_expressions) > 1:
            return SQLValidationResult(
                is_valid=False,
                errors=["Multiple SQL statements detected. Only single queries are permitted."],
            )

        ast = parsed_expressions[0]

        # 2. Operation Validation (Read-only check)
        if self.read_only:
            # Check root node
            if not isinstance(ast, (exp.Select, exp.Union)):
                errors.append(f"Operation '{ast.key.upper()}' is not permitted in read-only mode.")

            # Traverse AST to ensure no forbidden sub-nodes exist
            for forbidden_type in self.FORBIDDEN_EXPRESSION_TYPES:
                if list(ast.find_all(forbidden_type)):
                    errors.append(f"Forbidden data-modifying operation '{forbidden_type.__name__}' detected.")
                    break

        # 3. Query Complexity Check (Join count)
        joins = list(ast.find_all(exp.Join))
        if len(joins) > self.max_joins:
            errors.append(
                f"Query complexity exceeded: query contains {len(joins)} joins (maximum allowed is {self.max_joins})."
            )

        # 4. Table and Schema Allowlist Validation
        tables_used: List[str] = []
        # Find all table references
        table_nodes = list(ast.find_all(exp.Table))

        # Ignore CTE aliases from table check
        cte_aliases: Set[str] = set()
        for with_node in ast.find_all(exp.With):
            for cte in with_node.expressions:
                if hasattr(cte, "alias") and cte.alias:
                    cte_aliases.add(cte.alias.lower())

        for tbl_node in table_nodes:
            t_name = tbl_node.name.lower() if tbl_node.name else ""
            s_name = tbl_node.db.lower() if tbl_node.db else ""

            # Skip CTE aliases
            if t_name in cte_aliases:
                continue

            full_name = f"{s_name}.{t_name}" if s_name else t_name
            tables_used.append(full_name)

            # Check schema allowlist if configured and schema was specified
            if s_name and self.allowed_schemas and s_name not in self.allowed_schemas:
                errors.append(
                    f"Access to schema '{s_name}' is not permitted. Allowed schemas: {sorted(list(self.allowed_schemas))}"
                )

            # Check table allowlist if configured
            if self.allowed_tables:
                # Allowed if either 'schema.table' or 'table' matches
                is_allowed = (
                    full_name in self.allowed_tables
                    or t_name in self.allowed_tables
                    or any(a.endswith(f".{t_name}") for a in self.allowed_tables)
                )
                if not is_allowed:
                    errors.append(
                        f"Access to table '{full_name}' is not permitted. Allowed tables: {sorted(list(self.allowed_tables))}"
                    )

        # 5. Column Allowlist Validation (if configured)
        columns_used: List[str] = []
        if self.allowed_columns:
            for col_node in ast.find_all(exp.Column):
                c_name = col_node.name.lower() if col_node.name else ""
                t_ref = col_node.table.lower() if col_node.table else ""
                if c_name and c_name != "*":
                    columns_used.append(c_name)
                    candidate_tables: List[str] = []
                    if t_ref:
                        candidate_tables = [t for t in self.allowed_columns if t == t_ref or t.endswith(f".{t_ref}")]
                    elif len(tables_used) == 1:
                        target = tables_used[0].lower()
                        candidate_tables = [t for t in self.allowed_columns if t == target or t.endswith(f".{target}")]
                    else:
                        candidate_tables = [t for t in self.allowed_columns if any(t == u or t.endswith(f".{u}") for u in tables_used)]

                    if candidate_tables:
                        allowed_in_any = any(c_name in self.allowed_columns[t] for t in candidate_tables)
                        if not allowed_in_any:
                            table_display = candidate_tables[0] if len(candidate_tables) == 1 else (t_ref or "query")
                            errors.append(f"Access to column '{table_display}.{c_name}' is not permitted.")
        else:
            for col_node in ast.find_all(exp.Column):
                c_name = col_node.name.lower() if col_node.name else ""
                if c_name and c_name != "*":
                    columns_used.append(c_name)

        # 6. Limit Enforcement
        if self.enforce_limit and isinstance(ast, exp.Select):
            limit_node = ast.args.get("limit")
            if limit_node is None:
                # Append LIMIT clause
                ast = ast.limit(self.max_rows)
                warnings.append(f"Appended default LIMIT {self.max_rows}")
            else:
                try:
                    current_limit = int(limit_node.expression.this)
                    if current_limit > self.max_rows:
                        ast = ast.limit(self.max_rows)
                        warnings.append(f"Capped requested LIMIT {current_limit} to maximum {self.max_rows}")
                except (ValueError, TypeError, AttributeError):
                    pass

        # Generate normalized cleaned SQL
        cleaned_sql = ast.sql(dialect=self.dialect)
        is_valid = len(errors) == 0

        return SQLValidationResult(
            is_valid=is_valid,
            cleaned_sql=cleaned_sql,
            tables_used=tables_used,
            columns_used=columns_used,
            operations=["SELECT"],
            errors=errors,
            warnings=warnings,
        )

    def validate_or_raise(self, sql_query: str) -> str:
        """Validate SQL query; returns cleaned SQL if valid, raises SQLValidationError otherwise."""
        result = self.validate(sql_query)
        if not result.is_valid:
            err_msg = "; ".join(result.errors)
            logger.warning(f"SQL validation blocked query: {err_msg}")
            raise SQLValidationError(
                message=f"SQL Validation Failed: {err_msg}",
                sql=sql_query,
                violation_type="security_policy",
            )
        return result.cleaned_sql
