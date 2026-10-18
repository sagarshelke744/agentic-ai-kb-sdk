"""Agentic KnowledgeBase SDK (agentic-kb).

Production-ready Agentic AI Database Knowledgebase platform.
"""

from agentic_kb.agent.agent import AgenticKnowledgeBase
from agentic_kb.database.base import BaseDatabaseProvider
from agentic_kb.database.factory import DatabaseProviderFactory
from agentic_kb.database.mock import MockDatabaseProvider
from agentic_kb.database.models import (
    ColumnMetadata,
    DatabaseSchemaMetadata,
    QueryResult,
    TableMetadata,
)
from agentic_kb.database.postgres import PostgreSQLProvider
from agentic_kb.exceptions.errors import (
    AgenticKBError,
    ConfigurationError,
    DatabaseConnectionError,
    DatabaseError,
    DatabaseTimeoutError,
    KnowledgeBaseError,
    LLMError,
    LLMMalformedOutputError,
    LLMRateLimitError,
    LLMTimeoutError,
    PermissionDeniedError,
    PromptInjectionError,
    QueryExecutionError,
    SQLValidationError,
    SecurityError,
    VectorStoreError,
)
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
from agentic_kb.llm.azure import AzureOpenAIProvider
from agentic_kb.llm.base import BaseLLMProvider, LLMMessage, LLMResult, TokenUsage
from agentic_kb.llm.custom import CustomCallableProvider, FallbackLLMProvider
from agentic_kb.llm.factory import LLMProviderFactory
from agentic_kb.llm.gemini import GeminiProvider
from agentic_kb.llm.groq import GroqProvider
from agentic_kb.llm.mock import MockLLMProvider
from agentic_kb.llm.openai import OpenAIProvider
from agentic_kb.models.config import (
    AgentConfig,
    AgenticKBConfig,
    ConversationConfig,
    DatabaseConfig,
    KnowledgeBaseConfig,
    LLMConfig,
    ResponseConfig,
    SecurityConfig,
)
from agentic_kb.models.request import ChatRequest
from agentic_kb.models.response import AgentMetadata, ChatResponse, StreamChunk
from agentic_kb.security.permissions import PermissionEngine
from agentic_kb.security.sanitizer import DataMasker, InputSanitizer
from agentic_kb.security.sql_validator import SQLValidationResult, SQLValidator

__version__ = "0.1.0"

__all__ = [
    # Core Agent
    "AgenticKnowledgeBase",
    # Knowledgebase & Semantic Layer
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
    # Database Abstractions & Providers
    "BaseDatabaseProvider",
    "PostgreSQLProvider",
    "MockDatabaseProvider",
    "DatabaseProviderFactory",
    "ColumnMetadata",
    "TableMetadata",
    "DatabaseSchemaMetadata",
    "QueryResult",
    # Security & Guardrails
    "SQLValidator",
    "SQLValidationResult",
    "InputSanitizer",
    "DataMasker",
    "PermissionEngine",
    # LLM Abstractions & Providers
    "BaseLLMProvider",
    "LLMMessage",
    "LLMResult",
    "TokenUsage",
    "LLMProviderFactory",
    "OpenAIProvider",
    "AzureOpenAIProvider",
    "GeminiProvider",
    "GroqProvider",
    "MockLLMProvider",
    "CustomCallableProvider",
    "FallbackLLMProvider",
    # Configuration
    "AgenticKBConfig",
    "AgentConfig",
    "LLMConfig",
    "DatabaseConfig",
    "KnowledgeBaseConfig",
    "SecurityConfig",
    "ResponseConfig",
    "ConversationConfig",
    # Models
    "ChatRequest",
    "ChatResponse",
    "AgentMetadata",
    "StreamChunk",
    # Exceptions
    "AgenticKBError",
    "ConfigurationError",
    "SecurityError",
    "SQLValidationError",
    "PermissionDeniedError",
    "PromptInjectionError",
    "DatabaseError",
    "DatabaseConnectionError",
    "DatabaseTimeoutError",
    "QueryExecutionError",
    "LLMError",
    "LLMTimeoutError",
    "LLMRateLimitError",
    "LLMMalformedOutputError",
    "KnowledgeBaseError",
    "VectorStoreError",
]
