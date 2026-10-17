"""Knowledgebase metadata models, business terms, and normalization store."""

import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agentic_kb.database.models import DatabaseSchemaMetadata, TableMetadata


class BusinessTerm(BaseModel):
    """
    Business semantic definition mapping colloquial business terms
    to specific database tables, columns, and filters (Section 15 of PRD).
    """

    term: str = Field(..., description="Business term name (e.g. 'revenue', 'active_customer')")
    definition: str = Field(..., description="Explanation of what this metric or concept means")
    table: Optional[str] = Field(default=None, description="Primary database table implementing this term")
    column: Optional[str] = Field(default=None, description="Primary column implementing this term")
    filter: Optional[str] = Field(default=None, description="SQL WHERE filter required for this term (e.g. status = 'COMPLETED')")
    synonyms: List[str] = Field(default_factory=list, description="Common alternative names or phrases")

    def to_prompt_context(self) -> str:
        parts = [f"Term '{self.term}': {self.definition}"]
        if self.table:
            parts.append(f"  Mapped Table: {self.table}")
        if self.column:
            parts.append(f"  Mapped Column: {self.column}")
        if self.filter:
            parts.append(f"  Mandatory SQL Filter: {self.filter}")
        if self.synonyms:
            parts.append(f"  Synonyms: {', '.join(self.synonyms)}")
        return "\n".join(parts)


class KnowledgeDocument(BaseModel):
    """Atomic searchable piece of knowledge in the semantic index."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(..., description="Title of document or object name")
    content: str = Field(..., description="Searchable textual content")
    doc_type: str = Field(..., description="Category: 'table', 'column', 'business_term', 'rule', 'sample_query'")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata tags (table name, schema, etc.)")
    embedding: Optional[List[float]] = Field(default=None, description="Vector embedding representation")


class NormalizedMetadataStore:
    """
    Transforms relational database schema catalogs, user-provided descriptions,
    business rules, and business terms into normalized KnowledgeDocuments.
    """

    @classmethod
    def normalize_table(
        cls,
        table: TableMetadata,
        table_description_override: Optional[str] = None,
        column_descriptions_override: Optional[Dict[str, str]] = None,
    ) -> KnowledgeDocument:
        """Create a KnowledgeDocument from a TableMetadata instance."""
        desc = table_description_override or table.description or "No description provided."
        col_overrides = column_descriptions_override or {}

        # Build rich searchable document text
        content_lines = [
            f"Table: {table.full_name}",
            f"Description: {desc}",
            "Columns:",
        ]

        for col in table.columns:
            col_desc = col_overrides.get(col.name) or col.description
            col_info = f"  - {col.name} ({col.data_type})"
            if col.is_primary_key:
                col_info += " [PRIMARY KEY]"
            if col.is_foreign_key and col.foreign_table:
                col_info += f" [REFERENCES {col.foreign_table}]"
            if col_desc:
                col_info += f": {col_desc}"
            content_lines.append(col_info)

        return KnowledgeDocument(
            id=f"table:{table.full_name}",
            title=f"Table {table.full_name}",
            content="\n".join(content_lines),
            doc_type="table",
            metadata={
                "table_name": table.table_name,
                "full_name": table.full_name,
                "schema_name": table.schema_name,
            },
        )

    @classmethod
    def normalize_business_term(cls, term: BusinessTerm) -> KnowledgeDocument:
        """Create a KnowledgeDocument from a BusinessTerm."""
        content = term.to_prompt_context()
        return KnowledgeDocument(
            id=f"term:{term.term.lower().replace(' ', '_')}",
            title=f"Business Term: {term.term}",
            content=content,
            doc_type="business_term",
            metadata={
                "term": term.term,
                "table": term.table,
                "column": term.column,
                "filter": term.filter,
            },
        )

    @classmethod
    def normalize_rule(cls, rule_text: str, idx: int) -> KnowledgeDocument:
        """Create a KnowledgeDocument from a business rule string."""
        return KnowledgeDocument(
            id=f"rule:{idx}",
            title=f"Business Rule #{idx}",
            content=rule_text,
            doc_type="rule",
            metadata={"rule_index": idx},
        )
