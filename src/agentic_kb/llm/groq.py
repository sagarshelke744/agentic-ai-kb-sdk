"""Groq LLM Provider implementation (OpenAI-compatible API)."""

import json
import os
import re
from typing import Any, List, Optional, Type, TypeVar

from pydantic import BaseModel

from agentic_kb.exceptions.errors import (
    ConfigurationError,
    LLMError,
    LLMMalformedOutputError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from agentic_kb.llm.base import LLMMessage
from agentic_kb.llm.openai import OpenAIProvider
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.llm.groq")
T = TypeVar("T", bound=BaseModel)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def _parse_duration(text: str) -> Optional[float]:
    """Parse Groq-style durations such as '7m12.5s', '1h2m3s', '850ms' or '2.5s' into seconds."""
    m = re.fullmatch(r"\s*(?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)s)?\s*", text)
    if m and any(m.groups()):
        h, mi, sec = m.groups()
        return int(h or 0) * 3600 + int(mi or 0) * 60 + float(sec or 0)
    m = re.fullmatch(r"\s*([\d.]+)ms\s*", text)
    return float(m.group(1)) / 1000 if m else None


class GroqProvider(OpenAIProvider):
    """
    Groq Cloud provider. Groq exposes an OpenAI-compatible endpoint, so this reuses the
    OpenAI client with Groq's base URL (or a custom gateway URL via `base_url`).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "llama-3.3-70b-versatile",
        base_url: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(
            api_key=api_key or os.getenv("GROQ_API_KEY"),
            model=model,
            base_url=base_url or os.getenv("GROQ_BASE_URL") or GROQ_BASE_URL,
            **kwargs,
        )

    @property
    def provider_name(self) -> str:
        return "groq"

    def _require_key(self) -> None:
        if not self.api_key:
            raise ConfigurationError(
                "Groq API key is missing. Provide `api_key` or set the `GROQ_API_KEY` environment variable."
            )

    def _get_client(self) -> Any:
        self._require_key()
        return super()._get_client()

    def _get_async_client(self) -> Any:
        self._require_key()
        return super()._get_async_client()

    # Groq's strict `json_schema` mode is only available on some models, whereas
    # `json_object` mode works everywhere, so structured output is done via JSON mode
    # with the schema spelled out in the prompt.
    def _structured_messages(self, messages: List[LLMMessage], response_model: Type[T]) -> List[LLMMessage]:
        schema = json.dumps(response_model.model_json_schema())
        augmented = list(messages)
        augmented.append(
            LLMMessage.user(f"Respond ONLY with a valid JSON object conforming to this JSON schema:\n{schema}")
        )
        return augmented

    def _parse_structured(self, content: str, response_model: Type[T]) -> T:
        text = (content or "{}").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            return response_model.model_validate_json(text)
        except Exception as e:
            raise LLMMalformedOutputError(
                f"Failed to validate Groq response as {response_model.__name__}: {str(e)}",
                raw_output=text,
            ) from e

    def generate_structured(
        self,
        messages: List[LLMMessage],
        response_model: Type[T],
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> T:
        result = self.generate(
            self._structured_messages(messages, response_model),
            temperature=temperature,
            response_format={"type": "json_object"},
            **kwargs,
        )
        return self._parse_structured(result.content, response_model)

    async def agenerate_structured(
        self,
        messages: List[LLMMessage],
        response_model: Type[T],
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> T:
        result = await self.agenerate(
            self._structured_messages(messages, response_model),
            temperature=temperature,
            response_format={"type": "json_object"},
            **kwargs,
        )
        return self._parse_structured(result.content, response_model)

    @staticmethod
    def _retry_after(err: Exception) -> Optional[float]:
        """Read the suggested wait from the Retry-After header or the 'try again in 7m12s' message."""
        headers = getattr(getattr(err, "response", None), "headers", None)
        if headers:
            value = headers.get("retry-after")
            if value:
                try:
                    return float(value)
                except ValueError:
                    pass
        m = re.search(r"try again in ([0-9hms.]+?)[.\s]*(?:$|[^0-9hms.])", str(err), re.I)
        return _parse_duration(m.group(1)) if m else None

    def _handle_api_error(self, err: Exception) -> None:
        err_type = type(err).__name__
        err_msg = str(err)
        lowered = err_msg.lower()

        if "RateLimit" in err_type or "rate_limit" in lowered or "rate limit" in lowered or "429" in lowered:
            raise LLMRateLimitError(provider="groq", retry_after=self._retry_after(err)) from err
        if "Timeout" in err_type or "timed out" in lowered:
            raise LLMTimeoutError(provider="groq", timeout_seconds=self.timeout_seconds) from err
        if "Authentication" in err_type or "invalid api key" in lowered or "401" in lowered:
            raise ConfigurationError("Groq rejected the API key. Check GROQ_API_KEY.") from err

        raise LLMError(f"Groq error: {err_msg}") from err
