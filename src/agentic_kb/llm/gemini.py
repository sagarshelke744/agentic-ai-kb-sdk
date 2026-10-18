"""Google Gemini LLM Provider implementation."""

import asyncio
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

logger = get_logger("agentic_kb.llm.gemini")
T = TypeVar("T", bound=BaseModel)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini model provider implementation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-1.5-pro",
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
        self.api_key = api_key
        self._client: Optional[Any] = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._client = genai.GenerativeModel(self.model)
            except ImportError:
                raise ConfigurationError(
                    "The 'google-generativeai' package is required for GeminiProvider. "
                    "Install it via `pip install google-generativeai`."
                )
        return self._client

    def _format_contents(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        contents = []
        for m in messages:
            role = "model" if m.role == "assistant" else "user"
            contents.append({"role": role, "parts": [m.content]})
        return contents

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
        contents = self._format_contents(messages)

        def _call() -> Any:
            try:
                gen_config = {"temperature": temp}
                if tokens:
                    gen_config["max_output_tokens"] = tokens
                return client.generate_content(contents, generation_config=gen_config)
            except Exception as e:
                self._handle_api_error(e)

        start = time.time()
        resp = self.execute_with_retry(_call, operation_name="Gemini Generate Content")
        duration = (time.time() - start) * 1000

        content = resp.text or ""
        usage = TokenUsage()
        if hasattr(resp, "usage_metadata") and resp.usage_metadata:
            usage = TokenUsage(
                prompt_tokens=getattr(resp.usage_metadata, "prompt_token_count", 0),
                completion_tokens=getattr(resp.usage_metadata, "candidates_token_count", 0),
                total_tokens=getattr(resp.usage_metadata, "total_token_count", 0),
            )
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
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate(messages, temperature=temperature, max_tokens=max_tokens, **kwargs),
        )

    def generate_structured(
        self,
        messages: List[LLMMessage],
        response_model: Type[T],
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> T:
        schema = response_model.model_json_schema()
        system_instruction = (
            f"\nYou must respond ONLY with valid JSON conforming to this schema:\n"
            f"{json.dumps(schema)}"
        )
        augmented = list(messages)
        augmented.append(LLMMessage.user(system_instruction))
        result = self.generate(augmented, temperature=temperature, **kwargs)

        text = result.content.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return response_model.model_validate_json(text)
        except Exception as e:
            raise LLMMalformedOutputError(
                f"Failed to validate Gemini response as {response_model.__name__}: {str(e)}",
                raw_output=text,
            ) from e

    async def agenerate_structured(
        self,
        messages: List[LLMMessage],
        response_model: Type[T],
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate_structured(messages, response_model, temperature=temperature, **kwargs),
        )

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
        contents = self._format_contents(messages)

        try:
            gen_config = {"temperature": temp}
            if tokens:
                gen_config["max_output_tokens"] = tokens
            response = client.generate_content(contents, generation_config=gen_config, stream=True)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            self._handle_api_error(e)

    async def astream(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        # Stream sync chunks in thread or async wrapper
        for chunk in self.stream(messages, temperature=temperature, max_tokens=max_tokens, **kwargs):
            yield chunk

    @staticmethod
    def _parse_retry_after(text: str) -> Optional[float]:
        """Extract Google's suggested retry delay ("retry in 11h27m46.7s" / "retry_delay { seconds: 23 }")."""
        import re

        m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", text, re.I)
        if m:
            h, mi, sec = m.groups()
            return int(h or 0) * 3600 + int(mi or 0) * 60 + float(sec)
        m = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", text, re.I)
        return float(m.group(1)) if m else None

    def _handle_api_error(self, err: Exception) -> None:
        err_msg = str(err).lower()
        if "quota" in err_msg or "rate limit" in err_msg or "resourceexhausted" in err_msg or "429" in err_msg:
            raise LLMRateLimitError(provider="gemini", retry_after=self._parse_retry_after(str(err))) from err
        if "timeout" in err_msg or "timed out" in err_msg or "deadline" in err_msg:
            raise LLMTimeoutError(provider="gemini", timeout_seconds=self.timeout_seconds) from err
        raise LLMError(f"Gemini error: {str(err)}") from err
