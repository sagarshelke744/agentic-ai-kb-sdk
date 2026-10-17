"""Generic and pluggable custom LLM adapters and fallbacks.

Allows developers to inject any callable, LangChain/LangGraph runnable,
or custom enterprise model gateway with minimal configuration.
"""

import asyncio
import json
import time
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Iterator,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
)
from pydantic import BaseModel

from agentic_kb.exceptions.errors import (
    ConfigurationError,
    LLMError,
    LLMMalformedOutputError,
)
from agentic_kb.llm.base import BaseLLMProvider, LLMMessage, LLMResult, TokenUsage
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.llm.custom")
T = TypeVar("T", bound=BaseModel)


class CustomCallableProvider(BaseLLMProvider):
    """
    Adapter that wraps any Python callable, LangGraph runnable, or LangChain model
    into the standard BaseLLMProvider interface.

    Example:
    ```python
    # 1. Simple function:
    def my_custom_llm(messages):
        return "Custom response from enterprise model"

    provider = CustomCallableProvider(generate_fn=my_custom_llm)

    # 2. Or a LangGraph / LangChain runnable:
    provider = CustomCallableProvider(
        generate_fn=lambda msgs: langchain_chain.invoke(msgs).content
    )
    ```
    """

    def __init__(
        self,
        generate_fn: Callable[..., Any],
        agenerate_fn: Optional[Callable[..., Any]] = None,
        structured_fn: Optional[Callable[..., Any]] = None,
        model: str = "custom-model",
        provider_name_override: str = "custom",
        **kwargs: Any,
    ):
        super().__init__(model=model, **kwargs)
        self._generate_fn = generate_fn
        self._agenerate_fn = agenerate_fn
        self._structured_fn = structured_fn
        self._provider_name = provider_name_override

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def generate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        start = time.time()
        try:
            # Check if callable accepts kwargs or just messages
            try:
                res = self._generate_fn(
                    messages,
                    temperature=temperature or self.temperature,
                    max_tokens=max_tokens or self.max_tokens,
                    **kwargs,
                )
            except TypeError:
                res = self._generate_fn(messages)

            content = str(res.content if hasattr(res, "content") else res)
            duration = (time.time() - start) * 1000
            usage = TokenUsage(
                prompt_tokens=sum(len(m.content) for m in messages) // 4,
                completion_tokens=len(content) // 4,
                total_tokens=(sum(len(m.content) for m in messages) + len(content)) // 4,
            )
            self.record_usage(usage)
            return LLMResult(
                content=content,
                token_usage=usage,
                duration_ms=duration,
                model=self.model,
                provider=self.provider_name,
                raw_response=res,
            )
        except Exception as e:
            logger.error(f"Error executing custom LLM callable: {str(e)}")
            raise LLMError(f"Custom LLM provider failed: {str(e)}") from e

    async def agenerate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        if self._agenerate_fn:
            start = time.time()
            try:
                res = await self._agenerate_fn(messages, **kwargs)
                content = str(res.content if hasattr(res, "content") else res)
                duration = (time.time() - start) * 1000
                return LLMResult(
                    content=content,
                    token_usage=TokenUsage(),
                    duration_ms=duration,
                    model=self.model,
                    provider=self.provider_name,
                )
            except Exception as e:
                raise LLMError(f"Custom async LLM provider failed: {str(e)}") from e
        # Run sync function in thread pool if no async function provided
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
        if self._structured_fn:
            return self._structured_fn(messages, response_model, **kwargs)

        # Default fallback: generate string, parse as JSON, validate against response_model
        system_instruction = (
            f"\n\nCRITICAL: Respond ONLY with valid JSON conforming to this JSON Schema:\n"
            f"{json.dumps(response_model.model_json_schema())}"
        )
        augmented_messages = list(messages)
        augmented_messages.append(LLMMessage.system(system_instruction))

        result = self.generate(augmented_messages, temperature=temperature, **kwargs)
        raw_text = result.content.strip()

        # Clean markdown codeblocks if returned
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

        try:
            parsed = json.loads(raw_text)
            return response_model.model_validate(parsed)
        except Exception as e:
            raise LLMMalformedOutputError(
                f"Custom LLM output could not be validated as {response_model.__name__}: {str(e)}",
                raw_output=raw_text,
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
        result = self.generate(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)
        yield result.content

    async def astream(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        result = await self.agenerate(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)
        yield result.content


class FallbackLLMProvider(BaseLLMProvider):
    """
    Wraps a primary and backup LLM provider.
    If the primary fails after retries, seamlessly delegates to the fallback provider.
    """

    def __init__(
        self,
        primary: BaseLLMProvider,
        fallbacks: List[BaseLLMProvider],
        model: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(model=model or primary.model, **kwargs)
        self.primary = primary
        self.fallbacks = fallbacks

    @property
    def provider_name(self) -> str:
        return f"fallback({self.primary.provider_name})"

    def generate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        try:
            return self.primary.generate(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)
        except Exception as e:
            logger.warning(
                f"Primary provider '{self.primary.provider_name}' failed: {str(e)}. "
                f"Trying fallback provider..."
            )
            for fb in self.fallbacks:
                try:
                    res = fb.generate(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)
                    self.record_usage(res.token_usage)
                    return res
                except Exception as fb_err:
                    logger.warning(f"Fallback provider '{fb.provider_name}' also failed: {str(fb_err)}")
            raise e

    async def agenerate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        try:
            return await self.primary.agenerate(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)
        except Exception as e:
            for fb in self.fallbacks:
                try:
                    res = await fb.agenerate(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)
                    self.record_usage(res.token_usage)
                    return res
                except Exception:
                    pass
            raise e

    def generate_structured(
        self,
        messages: List[LLMMessage],
        response_model: Type[T],
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> T:
        try:
            return self.primary.generate_structured(messages, response_model=response_model, **kwargs)
        except Exception as e:
            for fb in self.fallbacks:
                try:
                    return fb.generate_structured(messages, response_model=response_model, **kwargs)
                except Exception:
                    pass
            raise e

    async def agenerate_structured(
        self,
        messages: List[LLMMessage],
        response_model: Type[T],
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> T:
        try:
            return await self.primary.agenerate_structured(messages, response_model=response_model, **kwargs)
        except Exception as e:
            for fb in self.fallbacks:
                try:
                    return await fb.agenerate_structured(messages, response_model=response_model, **kwargs)
                except Exception:
                    pass
            raise e

    def stream(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        return self.primary.stream(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)

    async def astream(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        async for chunk in self.primary.astream(messages, temperature=temperature, max_tokens=max_tokens, **kwargs):
            yield chunk
