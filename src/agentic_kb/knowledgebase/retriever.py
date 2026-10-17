"""Semantic vector stores and knowledge retrieval engine."""

import abc
import math
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agentic_kb.knowledgebase.embeddings import BaseEmbeddingProvider
from agentic_kb.knowledgebase.metadata import KnowledgeDocument
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.knowledgebase.retriever")


class SearchResult(BaseModel):
    """Vector search result hit with similarity score."""

    document: KnowledgeDocument
    score: float = Field(..., description="Cosine similarity score (0.0 to 1.0)")


class RetrievalContext(BaseModel):
    """Filtered, relevant domain context retrieved for a specific user question."""

    relevant_tables: List[str] = Field(default_factory=list, description="Relevant table full_names")
    relevant_terms: List[str] = Field(default_factory=list, description="Relevant business terms")
    relevant_rules: List[str] = Field(default_factory=list, description="Relevant business rules")
    formatted_prompt_context: str = Field(default="", description="Ready-to-inject LLM prompt snippet")
    search_results: List[SearchResult] = Field(default_factory=list)


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm1 * norm2)))


class BaseVectorStore(abc.ABC):
    """Abstract interface for vector similarity stores."""

    @abc.abstractmethod
    def add_documents(self, documents: List[KnowledgeDocument]) -> None:
        """Add and index documents with their embeddings."""
        pass

    @abc.abstractmethod
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        doc_types: Optional[List[str]] = None,
    ) -> List[SearchResult]:
        """Perform nearest neighbor search by vector cosine similarity."""
        pass


class InMemoryVectorStore(BaseVectorStore):
    """
    In-memory vector store computing exact cosine similarity.
    Fast, thread-safe, and requires zero external database dependencies.
    """

    def __init__(self):
        self._documents: Dict[str, KnowledgeDocument] = {}

    def add_documents(self, documents: List[KnowledgeDocument]) -> None:
        for doc in documents:
            if doc.embedding is None:
                logger.warning(f"Document '{doc.id}' has no embedding, skipping vector indexing.")
                continue
            self._documents[doc.id] = doc

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        doc_types: Optional[List[str]] = None,
    ) -> List[SearchResult]:
        results: List[SearchResult] = []
        for doc in self._documents.values():
            if doc_types and doc.doc_type not in doc_types:
                continue
            if not doc.embedding:
                continue
            sim = cosine_similarity(query_embedding, doc.embedding)
            results.append(SearchResult(document=doc, score=sim))

        # Sort descending by similarity score
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def count(self) -> int:
        return len(self._documents)


class KnowledgeRetriever:
    """
    Orchestrates semantic retrieval over the knowledgebase.
    Takes a natural language question -> embeds query -> retrieves matching tables,
    terms, and rules -> builds compact context for the SQL generator.
    """

    def __init__(
        self,
        vector_store: BaseVectorStore,
        embedding_provider: BaseEmbeddingProvider,
        top_k: int = 5,
        min_score: float = 0.0,
    ):
        self.vector_store = vector_store
        self.embedding_provider = embedding_provider
        self.top_k = top_k
        self.min_score = min_score

    def retrieve_context(self, question: str, top_k: Optional[int] = None) -> RetrievalContext:
        k = top_k or self.top_k
        query_vec = self.embedding_provider.embed_text(question)
        hits = self.vector_store.search(query_vec, top_k=k)

        # Filter by minimum score
        valid_hits = [h for h in hits if h.score >= self.min_score]

        tables: List[str] = []
        terms: List[str] = []
        rules: List[str] = []
        context_blocks: List[str] = []

        for hit in valid_hits:
            doc = hit.document
            if doc.doc_type == "table":
                tbl_name = doc.metadata.get("full_name") or doc.metadata.get("table_name")
                if tbl_name and tbl_name not in tables:
                    tables.append(tbl_name)
                    context_blocks.append(f"### Relevant Table: {tbl_name}\n{doc.content}")
            elif doc.doc_type == "business_term":
                term_name = doc.metadata.get("term")
                if term_name and term_name not in terms:
                    terms.append(term_name)
                    context_blocks.append(f"### Business Term Definition:\n{doc.content}")
            elif doc.doc_type == "rule":
                rules.append(doc.content)
                context_blocks.append(f"### Business Rule:\n{doc.content}")

        formatted_context = "\n\n".join(context_blocks)

        return RetrievalContext(
            relevant_tables=tables,
            relevant_terms=terms,
            relevant_rules=rules,
            formatted_prompt_context=formatted_context,
            search_results=valid_hits,
        )
