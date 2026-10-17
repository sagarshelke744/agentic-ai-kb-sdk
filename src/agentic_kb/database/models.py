"""Database schema metadata models and query result containers."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ColumnMetadata(BaseModel):
    """Metadata describing a single database column."""

    name: str = Field(..., description="Column name")
    data_type: str = Field(..., description="Data type representation (e.g., VARCHAR(255), INTEGER, TIMESTAMP)")
    is_nullable: bool = Field(default=True, description="Whether the column allows NULL values")
    is_primary_key: bool = Field(default=False, description="Whether the column is part of the primary key")
    is_foreign_key: bool = Field(default=False, description="Whether the column references a foreign key")
    foreign_table: Optional[str] = Field(default=None, description="Referenced table if foreign key")
    foreign_column: Optional[str] = Field(default=None, description="Referenced column if foreign key")
    description: Optional[str] = Field(default=None, description="Column comment or business definition")
    default_value: Optional[str] = Field(default=None, description="Default column value or expression")

    def to_ddl_fragment(self) -> str:
        """Render column as concise text for LLM prompts."""
        parts = [f"{self.name} {self.data_type}"]
        if self.is_primary_key:
            parts.append("PRIMARY KEY")
        elif not self.is_nullable:
            parts.append("NOT NULL")
        if self.is_foreign_key and self.foreign_table and self.foreign_column:
            parts.append(f"REFERENCES {self.foreign_table}({self.foreign_column})")
        if self.description:
            parts.append(f"-- {self.description}")
        return " ".join(parts)


class TableMetadata(BaseModel):
    """Metadata describing a single database table."""

    schema_name: str = Field(default="public", description="Schema name")
    table_name: str = Field(..., description="Table name")
    full_name: str = Field(..., description="Fully-qualified name (e.g. sales.orders)")
    columns: List[ColumnMetadata] = Field(default_factory=list, description="List of columns")
    primary_keys: List[str] = Field(default_factory=list, description="Primary key column names")
    foreign_keys: List[Dict[str, Any]] = Field(default_factory=list, description="Foreign key constraint mappings")
    indexes: List[str] = Field(default_factory=list, description="List of index names")
    description: Optional[str] = Field(default=None, description="Table comment or business definition")
    estimated_row_count: Optional[int] = Field(default=None, description="Estimated total rows")

    def get_column(self, col_name: str) -> Optional[ColumnMetadata]:
        for col in self.columns:
            if col.name.lower() == col_name.lower():
                return col
        return None

    def to_prompt_context(self, allowed_columns: Optional[List[str]] = None) -> str:
        """Format table schema for LLM SQL generation prompts."""
        lines = [f"Table: {self.full_name}"]
        if self.description:
            lines.append(f"  Description: {self.description}")
        lines.append("  Columns:")
        for col in self.columns:
            if allowed_columns is not None and col.name.lower() not in [c.lower() for c in allowed_columns]:
                continue
            lines.append(f"    - {col.to_ddl_fragment()}")
        return "\n".join(lines)


class DatabaseSchemaMetadata(BaseModel):
    """Complete catalog of discovered metadata across all allowed database objects."""

    dialect: str = Field(..., description="Database dialect (e.g., postgresql, sqlite, sqlserver)")
    database_name: str = Field(..., description="Name of the database")
    tables: Dict[str, TableMetadata] = Field(default_factory=dict, description="Mapping of full_name -> TableMetadata")
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def get_table(self, full_name: str) -> Optional[TableMetadata]:
        """Lookup table case-insensitively by full_name or table_name."""
        target = full_name.lower()
        for k, v in self.tables.items():
            if k.lower() == target or v.table_name.lower() == target:
                return v
        return None

    def to_prompt_context(self, table_names: Optional[List[str]] = None) -> str:
        """Format the entire or filtered schema catalog for LLM system prompts."""
        lines = []
        for name, table in self.tables.items():
            if table_names is not None and name.lower() not in [t.lower() for t in table_names]:
                continue
            lines.append(table.to_prompt_context())
            lines.append("")
        return "\n".join(lines).strip()


class QueryResult(BaseModel):
    """Normalized result of a safe database query execution."""

    columns: List[str] = Field(default_factory=list, description="Column names in order")
    rows: List[Dict[str, Any]] = Field(default_factory=list, description="Returned rows as dicts")
    row_count: int = Field(default=0, ge=0)
    duration_ms: float = Field(default=0.0, ge=0.0)
    is_truncated: bool = Field(default=False, description="Whether rows were truncated by max_rows limit")
    query: str = Field(..., description="The SQL query that was executed")
