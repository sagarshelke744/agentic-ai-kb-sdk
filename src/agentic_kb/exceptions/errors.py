"""Exception hierarchy for agentic-kb SDK."""

from typing import Optional, Dict, Any


class AgenticKBError(Exception):
    """Base exception for all agentic-kb errors."""

    def __init__(
        self,
        message: str,
        user_safe_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.user_safe_message = (
            user_safe_message
            or "An unexpected error occurred while processing your request. Please try again."
        )
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to a structured dictionary (safe for logging/responses)."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "user_safe_message": self.user_safe_message,
            "details": self.details,
        }


# Configuration Errors
class ConfigurationError(AgenticKBError):
    """Raised when configuration is invalid, missing, or malformed."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            user_safe_message="System configuration error. Please contact the administrator.",
            details=details,
        )


# Security and Validation Errors
class SecurityError(AgenticKBError):
    """Base class for security and authorization violations."""


class SQLValidationError(SecurityError):
    """Raised when generated SQL fails parsing or security policy validation."""

    def __init__(self, message: str, sql: Optional[str] = None, violation_type: Optional[str] = None):
        details = {}
        if violation_type:
            details["violation_type"] = violation_type
        # Do not expose raw internal SQL in user-safe message
        super().__init__(
            message=message,
            user_safe_message="The generated query did not pass security validation and was blocked.",
            details=details,
        )
        self.sql = sql


class PermissionDeniedError(SecurityError):
    """Raised when access to a disallowed schema, table, column, or row is attempted."""

    def __init__(self, resource: str, details: Optional[Dict[str, Any]] = None):
        message = f"Access denied to resource: '{resource}'"
        super().__init__(
            message=message,
            user_safe_message="You do not have permission to access the requested data.",
            details=details or {"resource": resource},
        )


class PromptInjectionError(SecurityError):
    """Raised when prompt injection or jailbreak attempt is detected."""

    def __init__(self, reason: str = "Suspicious input detected"):
        super().__init__(
            message=f"Prompt injection detected: {reason}",
            user_safe_message="Your request could not be processed due to safety policy restrictions.",
        )


# Database Errors
class DatabaseError(AgenticKBError):
    """Base class for database operations errors."""


class DatabaseConnectionError(DatabaseError):
    """Raised when unable to establish connection to the database."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            user_safe_message="Database service is currently unavailable. Please try again later.",
            details=details,
        )


class DatabaseTimeoutError(DatabaseError):
    """Raised when a database query exceeds configured execution timeout."""

    def __init__(self, timeout_seconds: float):
        super().__init__(
            message=f"Database query exceeded timeout of {timeout_seconds}s",
            user_safe_message="The database query timed out. Please try narrowing your query criteria or date range.",
            details={"timeout_seconds": timeout_seconds},
        )


class QueryExecutionError(DatabaseError):
    """Raised when SQL execution fails in the database engine."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            user_safe_message="An error occurred while retrieving data from the database.",
            details=details,
        )


# LLM Errors
class LLMError(AgenticKBError):
    """Base class for LLM provider errors."""


class LLMTimeoutError(LLMError):
    """Raised when an LLM provider request times out."""

    def __init__(self, provider: str, timeout_seconds: float):
        super().__init__(
            message=f"LLM provider '{provider}' timed out after {timeout_seconds}s",
            user_safe_message="The AI model took too long to respond. Please try asking again.",
            details={"provider": provider, "timeout_seconds": timeout_seconds},
        )


class LLMRateLimitError(LLMError):
    """Raised when LLM provider rate limits are exceeded."""

    def __init__(self, provider: str):
        super().__init__(
            message=f"LLM provider '{provider}' rate limit exceeded",
            user_safe_message="The AI service is experiencing high demand. Please try again in a moment.",
            details={"provider": provider},
        )


class LLMMalformedOutputError(LLMError):
    """Raised when LLM output does not match expected structure or JSON format."""

    def __init__(self, message: str, raw_output: Optional[str] = None):
        super().__init__(
            message=message,
            user_safe_message="Unable to parse the AI model's response. Please try rephrasing your question.",
        )
        self.raw_output = raw_output


# Knowledgebase & Retrieval Errors
class KnowledgeBaseError(AgenticKBError):
    """Base class for knowledgebase and vector store errors."""


class VectorStoreError(KnowledgeBaseError):
    """Raised when vector search or embedding generation fails."""
