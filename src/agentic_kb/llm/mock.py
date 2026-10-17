"""Mock LLM Provider for offline testing, local development, and CI."""

import json
import time
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
)
from pydantic import BaseModel

from agentic_kb.exceptions.errors import LLMMalformedOutputError
from agentic_kb.llm.base import BaseLLMProvider, LLMMessage, LLMResult, TokenUsage

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider(BaseLLMProvider):
    """
    Mock LLM provider useful for zero-cost unit testing, offline testing,
    and simulated agentic workflows.
    """

    def __init__(
        self,
        model: str = "mock-model",
        default_response: str = "Mock generated response",
        structured_responses: Optional[Dict[str, BaseModel]] = None,
        responses: Optional[List[Union[str, Exception]]] = None,
        response_generator: Optional[Callable[[List[LLMMessage]], str]] = None,
        **kwargs: Any,
    ):
        super().__init__(model=model, **kwargs)
        self.default_response = default_response
        self.structured_responses = structured_responses or {}
        self.responses = list(responses) if responses else []
        self.response_generator = response_generator
        self.history: List[List[LLMMessage]] = []

    @property
    def provider_name(self) -> str:
        return "mock"

    def _get_next_response(self, messages: List[LLMMessage]) -> str:
        self.history.append(messages)
        if self.responses:
            item = self.responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        if self.response_generator:
            return self.response_generator(messages)
        return self.default_response

    def generate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        start = time.time()
        content = self._get_next_response(messages)
        prompt_chars = sum(len(m.content) for m in messages)
        usage = TokenUsage(
            prompt_tokens=max(1, prompt_chars // 4),
            completion_tokens=max(1, len(content) // 4),
            total_tokens=max(2, (prompt_chars + len(content)) // 4),
            estimated_cost_usd=0.0,
        )
        self.record_usage(usage)
        duration = (time.time() - start) * 1000
        return LLMResult(
            content=content,
            token_usage=usage,
            duration_ms=duration,
            model=self.model,
            provider=self.provider_name,
        )

    async def agenerate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        return self.generate(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)

    def generate_structured(
        self,
        messages: List[LLMMessage],
        response_model: Type[T],
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> T:
        model_name = response_model.__name__
        if model_name in self.structured_responses:
            instance = self.structured_responses[model_name]
            if isinstance(instance, response_model):
                return instance

        raw = self._get_next_response(messages)
        try:
            parsed = json.loads(raw)
            return response_model.model_validate(parsed)
        except Exception as e:
            # If default string response isn't json, try constructing with dummy fields or raise
            raise LLMMalformedOutputError(
                f"Failed to parse mock structured output for {model_name}: {str(e)}",
                raw_output=raw,
            ) from e

    async def agenerate_structured(
        self,
        messages: List[LLMMessage],
        response_model: Type[T],
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> T:
        return self.generate_structured(messages, response_model=response_model, **kwargs)

    def stream(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        content = self._get_next_response(messages)
        for word in content.split(" "):
            yield word + " "

    async def astream(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        content = self._get_next_response(messages)
        for word in content.split(" "):
            yield word + " "
