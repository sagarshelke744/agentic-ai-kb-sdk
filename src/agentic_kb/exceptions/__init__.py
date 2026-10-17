"""Exceptions module for agentic-kb."""

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

__all__ = [
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
