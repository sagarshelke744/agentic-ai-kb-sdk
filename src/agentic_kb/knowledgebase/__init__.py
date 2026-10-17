"""Knowledgebase and semantic retrieval module."""

from agentic_kb.knowledgebase.embeddings import (
    BaseEmbeddingProvider,
    EmbeddingProviderFactory,
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from agentic_kb.knowledgebase.kb import KnowledgeBase
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
    SearchResult,
    cosine_similarity,
)

__all__ = [
    "KnowledgeBase",
    "BusinessTerm",
    "KnowledgeDocument",
    "NormalizedMetadataStore",
    "BaseEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "MockEmbeddingProvider",
    "EmbeddingProviderFactory",
    "BaseVectorStore",
    "InMemoryVectorStore",
    "KnowledgeRetriever",
    "RetrievalContext",
    "SearchResult",
    "cosine_similarity",
]
