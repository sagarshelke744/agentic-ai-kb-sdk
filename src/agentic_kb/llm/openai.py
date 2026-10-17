"""OpenAI LLM Provider implementation."""

import os
import json
import time
from typing import (
    Any,
    AsyncIterator,
    Dict,
    Iterator,
    List,
    Optional,
    Type,
    TypeVar,
)
from pydantic import BaseModel

from agentic_kb.exceptions.errors import (
    ConfigurationError,
    LLMError,
    LLMMalformedOutputError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from agentic_kb.llm.base import BaseLLMProvider, LLMMessage, LLMResult, TokenUsage
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.llm.openai")
T = TypeVar("T", bound=BaseModel)


class OpenAIProvider(BaseLLMProvider):
    """
    OpenAI and OpenAI-compatible API provider (supports GPT-4o, GPT-3.5,
    or local models via base_url like vLLM / Ollama).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = 2000,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        **kwargs: Any,
    ):
        super().__init__(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            **kwargs,
        )
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url
        self.organization = organization
        self._client: Optional[Any] = None
        self._async_client: Optional[Any] = None

    @property
    def provider_name(self) -> str:
        return "openai"

    def _get_client(self) -> Any:
        if self._client is None:
            if not self.api_key:
                raise ConfigurationError(
                    "OpenAI API key is missing. Please provide `api_key` or set the `OPENAI_API_KEY` environment variable."
                )
            try:
                from openai import OpenAI
            except ImportError:
                raise ConfigurationError(
                    "The 'openai' package is required to use OpenAIProvider. "
                    "Install it with `pip install openai` or `pip install agentic-kb[llm]`."
                )
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                organization=self.organization,
                timeout=self.timeout_seconds,
            )
        return self._client

    def _get_async_client(self) -> Any:
        if self._async_client is None:
            if not self.api_key:
                raise ConfigurationError(
                    "OpenAI API key is missing. Please provide `api_key` or set the `OPENAI_API_KEY` environment variable."
                )
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ConfigurationError(
                    "The 'openai' package is required to use OpenAIProvider. "
                    "Install it with `pip install openai` or `pip install agentic-kb[llm]`."
                )
            self._async_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                organization=self.organization,
                timeout=self.timeout_seconds,
            )
        return self._async_client

    def _format_messages(self, messages: List[LLMMessage]) -> List[Dict[str, str]]:
        formatted = []
        for m in messages:
            msg = {"role": m.role, "content": m.content}
            if m.name:
                msg["name"] = m.name
            formatted.append(msg)
        return formatted

    def _extract_usage(self, response: Any) -> TokenUsage:
        usage = getattr(response, "usage", None)
        if usage:
            return TokenUsage(
                prompt_tokens=getattr(usage, "prompt_tokens", 0),
                completion_tokens=getattr(usage, "completion_tokens", 0),
                total_tokens=getattr(usage, "total_tokens", 0),
            )
        return TokenUsage()

    def generate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        client = self._get_client()
        temp = self.temperature if temperature is None else temperature
        tokens = self.max_tokens if max_tokens is None else max_tokens
        formatted = self._format_messages(messages)

        def _call() -> Any:
            try:
                return client.chat.completions.create(
                    model=self.model,
                    messages=formatted,
                    temperature=temp,
                    max_tokens=tokens,
                    **kwargs,
                )
            except Exception as e:
                self._handle_api_error(e)

        start = time.time()
        resp = self.execute_with_retry(_call, operation_name="OpenAI Chat Completion")
        duration = (time.time() - start) * 1000

        content = resp.choices[0].message.content or ""
        usage = self._extract_usage(resp)
        self.record_usage(usage)

        return LLMResult(
            content=content,
            token_usage=usage,
            duration_ms=duration,
            model=self.model,
            provider=self.provider_name,
            raw_response=resp,
        )

    async def agenerate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        client = self._get_async_client()
        temp = self.temperature if temperature is None else temperature
        tokens = self.max_tokens if max_tokens is None else max_tokens
        formatted = self._format_messages(messages)

        async def _call() -> Any:
            try:
                return await client.chat.completions.create(
                    model=self.model,
                    messages=formatted,
                    temperature=temp,
                    max_tokens=tokens,
                    **kwargs,
                )
            except Exception as e:
                self._handle_api_error(e)

        start = time.time()
        resp = await self.aexecute_with_retry(_call, operation_name="Async OpenAI Chat Completion")
        duration = (time.time() - start) * 1000

        content = resp.choices[0].message.content or ""
        usage = self._extract_usage(resp)
        self.record_usage(usage)

        return LLMResult(
            content=content,
            token_usage=usage,
            duration_ms=duration,
            model=self.model,
            provider=self.provider_name,
            raw_response=resp,
        )

    def generate_structured(
        self,
        messages: List[LLMMessage],
        response_model: Type[T],
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> T:
        client = self._get_client()
        temp = self.temperature if temperature is None else temperature
        formatted = self._format_messages(messages)

        def _call() -> Any:
            try:
                # Use OpenAI's structured outputs parsing if available
                if hasattr(client.beta.chat.completions, "parse"):
                    return client.beta.chat.completions.parse(
                        model=self.model,
                        messages=formatted,
                        response_format=response_model,
                        temperature=temp,
                        **kwargs,
                    )
                else:
                    return client.chat.completions.create(
                        model=self.model,
                        messages=formatted,
                        response_format={"type": "json_object"},
                        temperature=temp,
                        **kwargs,
                    )
            except Exception as e:
                self._handle_api_error(e)

        resp = self.execute_with_retry(_call, operation_name="OpenAI Structured Output")
        usage = self._extract_usage(resp)
        self.record_usage(usage)

        # Check if parsed directly
        choice = resp.choices[0]
        if hasattr(choice.message, "parsed") and choice.message.parsed is not None:
            return choice.message.parsed

        # Fallback parse from content
        content = choice.message.content or "{}"
        try:
            return response_model.model_validate_json(content)
        except Exception as e:
            raise LLMMalformedOutputError(
                f"Failed to validate response as {response_model.__name__}: {str(e)}",
                raw_output=content,
            ) from e

    async def agenerate_structured(
        self,
        messages: List[LLMMessage],
        response_model: Type[T],
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> T:
        client = self._get_async_client()
        temp = self.temperature if temperature is None else temperature
        formatted = self._format_messages(messages)

        async def _call() -> Any:
            try:
                if hasattr(client.beta.chat.completions, "parse"):
                    return await client.beta.chat.completions.parse(
                        model=self.model,
                        messages=formatted,
                        response_format=response_model,
                        temperature=temp,
                        **kwargs,
                    )
                else:
                    return await client.chat.completions.create(
                        model=self.model,
                        messages=formatted,
                        response_format={"type": "json_object"},
                        temperature=temp,
                        **kwargs,
                    )
            except Exception as e:
                self._handle_api_error(e)

        resp = await self.aexecute_with_retry(_call, operation_name="Async OpenAI Structured Output")
        usage = self._extract_usage(resp)
        self.record_usage(usage)

        choice = resp.choices[0]
        if hasattr(choice.message, "parsed") and choice.message.parsed is not None:
            return choice.message.parsed

        content = choice.message.content or "{}"
        try:
            return response_model.model_validate_json(content)
        except Exception as e:
            raise LLMMalformedOutputError(
                f"Failed to validate response as {response_model.__name__}: {str(e)}",
                raw_output=content,
            ) from e

    def stream(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        client = self._get_client()
        temp = self.temperature if temperature is None else temperature
        tokens = self.max_tokens if max_tokens is None else max_tokens
        formatted = self._format_messages(messages)

        try:
            response_stream = client.chat.completions.create(
                model=self.model,
                messages=formatted,
                temperature=temp,
                max_tokens=tokens,
                stream=True,
                **kwargs,
            )
            for chunk in response_stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            self._handle_api_error(e)

    async def astream(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        client = self._get_async_client()
        temp = self.temperature if temperature is None else temperature
        tokens = self.max_tokens if max_tokens is None else max_tokens
        formatted = self._format_messages(messages)

        try:
            response_stream = await client.chat.completions.create(
                model=self.model,
                messages=formatted,
                temperature=temp,
                max_tokens=tokens,
                stream=True,
                **kwargs,
            )
            async for chunk in response_stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            self._handle_api_error(e)

    def _handle_api_error(self, err: Exception) -> None:
        err_type = type(err).__name__
        err_msg = str(err)

        if "RateLimit" in err_type or "rate_limit" in err_msg.lower():
            raise LLMRateLimitError(provider="openai") from err
        if "Timeout" in err_type or "timed out" in err_msg.lower():
            raise LLMTimeoutError(provider="openai", timeout_seconds=self.timeout_seconds) from err

        raise LLMError(f"OpenAI error: {err_msg}") from err
