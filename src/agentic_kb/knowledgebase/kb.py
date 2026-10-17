"""Central KnowledgeBase service for semantic indexing and retrieval."""

from typing import Any, Dict, List, Optional
from agentic_kb.database.models import DatabaseSchemaMetadata
from agentic_kb.knowledgebase.embeddings import (
    BaseEmbeddingProvider,
    EmbeddingProviderFactory,
    MockEmbeddingProvider,
)
from agentic_kb.knowledgebase.metadata import (
    BusinessTerm,
    KnowledgeDocument,
    NormalizedMetadataStore,
)
from agentic_kb.knowledgebase.retriever import (
    BaseVectorStore,
    InMemoryVectorStore,
    KnowledgeRetriever,
    RetrievalContext,
)
from agentic_kb.models.config import KnowledgeBaseConfig
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.knowledgebase")


class KnowledgeBase:
    """
    Central Knowledgebase platform component (Section 14 of PRD).

    Maintains vector-indexed database metadata, column definitions,
    business terms, and business rules. Provides semantic retrieval so the SQL agent
    only receives relevant database objects rather than huge schema dumps.
    """

    def __init__(
        self,
        config: Optional[KnowledgeBaseConfig] = None,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
        vector_store: Optional[BaseVectorStore] = None,
    ):
        self.config = config or KnowledgeBaseConfig()
        self.embedding_provider = embedding_provider or MockEmbeddingProvider()
        self.vector_store = vector_store or InMemoryVectorStore()
        self.retriever = KnowledgeRetriever(
            vector_store=self.vector_store,
            embedding_provider=self.embedding_provider,
            top_k=5,
        )
        self._indexed_count = 0

    def index_schema(
        self,
        schema_metadata: DatabaseSchemaMetadata,
        table_descriptions: Optional[Dict[str, str]] = None,
        column_descriptions: Optional[Dict[str, str]] = None,
    ) -> int:
        """
        Normalize and vector-index all tables in the schema catalog.
        """
        tbl_descs = table_descriptions or self.config.table_descriptions
        col_descs = column_descriptions or self.config.column_descriptions
        docs: List[KnowledgeDocument] = []

        for full_name, table_meta in schema_metadata.tables.items():
            doc = NormalizedMetadataStore.normalize_table(
                table=table_meta,
                table_description_override=tbl_descs.get(full_name) or tbl_descs.get(table_meta.table_name),
                column_descriptions_override=col_descs,
            )
            # Generate embedding
            doc.embedding = self.embedding_provider.embed_text(doc.content)
            docs.append(doc)

        self.vector_store.add_documents(docs)
        self._indexed_count += len(docs)
        logger.info(f"Indexed {len(docs)} tables into KnowledgeBase vector store.")
        return len(docs)

    def index_business_terms(self, terms: List[BusinessTerm]) -> int:
        """Vector-index business metric and entity definitions."""
        docs: List[KnowledgeDocument] = []
        for term in terms:
            doc = NormalizedMetadataStore.normalize_business_term(term)
            doc.embedding = self.embedding_provider.embed_text(doc.content)
            docs.append(doc)

        self.vector_store.add_documents(docs)
        self._indexed_count += len(docs)
        logger.info(f"Indexed {len(docs)} business terms into KnowledgeBase vector store.")
        return len(docs)

    def index_rules(self, rules: List[str]) -> int:
        """Vector-index business logic and governance rules."""
        docs: List[KnowledgeDocument] = []
        for i, rule_text in enumerate(rules, start=1):
            doc = NormalizedMetadataStore.normalize_rule(rule_text, i)
            doc.embedding = self.embedding_provider.embed_text(doc.content)
            docs.append(doc)

        self.vector_store.add_documents(docs)
        self._indexed_count += len(docs)
        return len(docs)

    def retrieve(self, question: str, top_k: Optional[int] = None) -> RetrievalContext:
        """Retrieve relevant schema objects, business terms, and rules for a query."""
        return self.retriever.retrieve_context(question=question, top_k=top_k)

    def get_indexed_count(self) -> int:
        """Return total indexed knowledge items."""
        return self._indexed_count
