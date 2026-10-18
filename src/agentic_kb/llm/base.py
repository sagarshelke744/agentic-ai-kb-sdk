"""Base abstraction, message models, and token tracker for LLM providers."""

import abc
import asyncio
import random
import time
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Iterator,
    List,
    Literal,
    Optional,
    Type,
    TypeVar,
    Union,
)
from pydantic import BaseModel, Field

from agentic_kb.exceptions.errors import (
    LLMError,
    LLMMalformedOutputError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from agentic_kb.observability.events import emit
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.llm")

# Upper bound on how long a provider-hinted retry delay is honoured
MAX_RETRY_WAIT_SECONDS = 30.0

T = TypeVar("T", bound=BaseModel)


class LLMMessage(BaseModel):
    """Normalized message representation across all LLM providers."""

    role: Literal["system", "user", "assistant", "tool"] = Field(
        ..., description="Message author role"
    )
    content: str = Field(..., description="Text content of the message")
    name: Optional[str] = Field(
        default=None, description="Optional name identifier for tool or user"
    )

    @classmethod
    def system(cls, content: str) -> "LLMMessage":
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> "LLMMessage":
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str) -> "LLMMessage":
        return cls(role="assistant", content=content)


class TokenUsage(BaseModel):
    """Token consumption and cost tracking."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: Optional[float] = Field(default=None, ge=0.0)

    def add(self, other: "TokenUsage") -> "TokenUsage":
        """Accumulate token counts."""
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            estimated_cost_usd=(
                (self.estimated_cost_usd or 0.0) + (other.estimated_cost_usd or 0.0)
                if (self.estimated_cost_usd is not None or other.estimated_cost_usd is not None)
                else None
            ),
        )


class LLMResult(BaseModel):
    """Normalized output from any LLM provider."""

    content: str = Field(..., description="Generated text content")
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    duration_ms: float = Field(default=0.0, ge=0.0)
    model: str = Field(default="")
    provider: str = Field(default="")
    raw_response: Optional[Any] = Field(default=None, exclude=True)


class BaseLLMProvider(abc.ABC):
    """
    Abstract Base Class for all LLM providers.

    Developers can implement this interface to plug in any LLM service,
    LangChain/LangGraph model, custom enterprise proxy, or local model runner.
    """

    def __init__(
        self,
        model: str,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        **kwargs: Any,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.extra_kwargs = kwargs
        self.total_token_usage = TokenUsage()

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g., 'openai', 'azure', 'gemini', 'custom')."""
        pass

    @abc.abstractmethod
    def generate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        """Synchronously generate text response from messages."""
        pass

    @abc.abstractmethod
    async def agenerate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        """Asynchronously generate text response from messages."""
        pass

    @abc.abstractmethod
    def generate_structured(
        self,
        messages: List[LLMMessage],
        response_model: Type[T],
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> T:
        """Synchronously generate structured output validated against a Pydantic model."""
        pass

    @abc.abstractmethod
    async def agenerate_structured(
        self,
        messages: List[LLMMessage],
        response_model: Type[T],
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> T:
        """Asynchronously generate structured output validated against a Pydantic model."""
        pass

    @abc.abstractmethod
    def stream(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Synchronously stream response tokens."""
        pass

    @abc.abstractmethod
    async def astream(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Asynchronously stream response tokens."""
        pass

    def record_usage(self, usage: TokenUsage) -> None:
        """Accumulate usage metrics for observability."""
        self.total_token_usage = self.total_token_usage.add(usage)

    def execute_with_retry(
        self,
        func: Callable[[], Any],
        operation_name: str = "LLM Generation",
    ) -> Any:
        """
        Execute a synchronous callable with exponential backoff and jitter retry.
        Retries on rate limits, network blips, or timeouts; fails fast on authentication.
        """
        attempts = 0
        last_exception: Optional[Exception] = None

        while attempts <= self.max_retries:
            try:
                return func()
            except (LLMRateLimitError, LLMTimeoutError, ConnectionError, TimeoutError) as e:
                attempts += 1
                last_exception = e
                if attempts > self.max_retries:
                    break
                backoff = (2 ** attempts) * 0.5 + random.uniform(0.1, 0.5)
                hinted = getattr(e, "retry_after", None)
                if hinted and hinted > MAX_RETRY_WAIT_SECONDS:
                    # Quota-style limit (e.g. daily cap): waiting out the retries cannot help
                    raise
                if hinted:
                    backoff = min(float(hinted) + 0.5, MAX_RETRY_WAIT_SECONDS)
                emit(
                    "retry",
                    operation=operation_name,
                    attempt=attempts,
                    max_retries=self.max_retries,
                    wait_seconds=round(backoff, 1),
                    reason=type(e).__name__,
                )
                logger.warning(
                    f"{operation_name} failed with {type(e).__name__}: {str(e)}. "
                    f"Retrying attempt {attempts}/{self.max_retries} in {backoff:.2f}s..."
                )
                time.sleep(backoff)
            except Exception as e:
                # Do not retry unrecognized or non-transient exceptions
                raise

        raise last_exception or LLMError(f"{operation_name} failed after {self.max_retries} retries")

    async def aexecute_with_retry(
        self,
        func: Callable[[], Any],
        operation_name: str = "Async LLM Generation",
    ) -> Any:
        """Execute an asynchronous callable with exponential backoff and jitter retry."""
        attempts = 0
        last_exception: Optional[Exception] = None

        while attempts <= self.max_retries:
            try:
                return await func()
            except (LLMRateLimitError, LLMTimeoutError, ConnectionError, TimeoutError) as e:
                attempts += 1
                last_exception = e
                if attempts > self.max_retries:
                    break
                backoff = (2 ** attempts) * 0.5 + random.uniform(0.1, 0.5)
                hinted = getattr(e, "retry_after", None)
                if hinted and hinted > MAX_RETRY_WAIT_SECONDS:
                    # Quota-style limit (e.g. daily cap): waiting out the retries cannot help
                    raise
                if hinted:
                    backoff = min(float(hinted) + 0.5, MAX_RETRY_WAIT_SECONDS)
                emit(
                    "retry",
                    operation=operation_name,
                    attempt=attempts,
                    max_retries=self.max_retries,
                    wait_seconds=round(backoff, 1),
                    reason=type(e).__name__,
                )
                logger.warning(
                    f"{operation_name} failed with {type(e).__name__}: {str(e)}. "
                    f"Retrying attempt {attempts}/{self.max_retries} in {backoff:.2f}s..."
                )
                await asyncio.sleep(backoff)
            except Exception:
                raise

        raise last_exception or LLMError(f"{operation_name} failed after {self.max_retries} retries")
