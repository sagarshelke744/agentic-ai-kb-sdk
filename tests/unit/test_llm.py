"""Unit tests for Phase 2: LLM Layer (providers, structured outputs, fallbacks, retries)."""

import pytest
from pydantic import BaseModel, Field

from agentic_kb.exceptions.errors import (
    ConfigurationError,
    LLMError,
    LLMMalformedOutputError,
    LLMRateLimitError,
)
from agentic_kb.llm.base import BaseLLMProvider, LLMMessage, LLMResult, TokenUsage
from agentic_kb.llm.custom import CustomCallableProvider, FallbackLLMProvider
from agentic_kb.llm.factory import LLMProviderFactory
from agentic_kb.llm.mock import MockLLMProvider
from agentic_kb.agent.agent import AgenticKnowledgeBase


class SalesSummary(BaseModel):
    total_sales: float = Field(..., description="Total sales in dollars")
    currency: str = "USD"
    items_count: int


def test_mock_llm_provider_generation():
    provider = MockLLMProvider(default_response="Sales were 50,000 last month")
    messages = [
        LLMMessage.system("You are a financial analyst."),
        LLMMessage.user("What were our sales?"),
    ]
    result = provider.generate(messages)
    assert result.content == "Sales were 50,000 last month"
    assert result.provider == "mock"
    assert result.token_usage.total_tokens > 0
    assert provider.total_token_usage.total_tokens == result.token_usage.total_tokens


def test_mock_llm_structured_output():
    mock_obj = SalesSummary(total_sales=45200.50, currency="USD", items_count=120)
    provider = MockLLMProvider(structured_responses={"SalesSummary": mock_obj})

    parsed = provider.generate_structured(
        [LLMMessage.user("Summarize sales")],
        response_model=SalesSummary,
    )
    assert isinstance(parsed, SalesSummary)
    assert parsed.total_sales == 45200.50
    assert parsed.items_count == 120


def test_mock_llm_structured_output_json_string():
    json_text = '{"total_sales": 12345.67, "currency": "EUR", "items_count": 88}'
    provider = MockLLMProvider(default_response=json_text)

    parsed = provider.generate_structured(
        [LLMMessage.user("Summarize sales")],
        response_model=SalesSummary,
    )
    assert parsed.total_sales == 12345.67
    assert parsed.currency == "EUR"


def test_custom_callable_provider_injection():
    """Test that any developer can inject a custom function or LangGraph/LangChain runnable."""
    call_log = []

    def my_custom_model(messages, **kwargs):
        call_log.append(messages)
        return "Grounded answer from enterprise internal model."

    provider = CustomCallableProvider(
        generate_fn=my_custom_model,
        model="enterprise-llama",
        provider_name_override="internal-gateway",
    )

    result = provider.generate([LLMMessage.user("Hello")])
    assert result.content == "Grounded answer from enterprise internal model."
    assert result.provider == "internal-gateway"
    assert len(call_log) == 1

    # Inject into AgenticKnowledgeBase
    agent = AgenticKnowledgeBase(
        llm=provider,
        database={
            "type": "sqlite",
            "host": "localhost",
            "port": 5432,
            "database": "sales_db",
            "username": "user",
        },
    )
    assert agent.llm.provider_name == "internal-gateway"
    resp = agent.ask("What is the status?")
    assert "enterprise internal model" in resp.answer


def test_custom_callable_structured_output():
    # Callable that produces valid JSON
    def json_generator(messages, **kwargs):
        return '```json\n{"total_sales": 999.0, "currency": "USD", "items_count": 10}\n```'

    provider = CustomCallableProvider(generate_fn=json_generator)
    structured = provider.generate_structured(
        [LLMMessage.user("Parse sales")],
        response_model=SalesSummary,
    )
    assert structured.total_sales == 999.0
    assert structured.items_count == 10


def test_fallback_provider_resilience():
    # Primary fails with LLMRateLimitError
    primary = MockLLMProvider(
        responses=[LLMRateLimitError("Primary rate limited")],
        provider_name_override="mock-primary",
    )
    # Secondary succeeds
    secondary = MockLLMProvider(default_response="Success from backup provider")

    fallback_llm = FallbackLLMProvider(primary=primary, fallbacks=[secondary])
    result = fallback_llm.generate([LLMMessage.user("Try generate")])
    assert result.content == "Success from backup provider"


def test_llm_factory_registration():
    class CustomEchoProvider(BaseLLMProvider):
        @property
        def provider_name(self) -> str:
            return "echo"

        def generate(self, messages, **kwargs):
            return LLMResult(content=messages[-1].content, model=self.model, provider="echo")

        async def agenerate(self, messages, **kwargs):
            return self.generate(messages, **kwargs)

        def generate_structured(self, messages, response_model, **kwargs):
            raise NotImplementedError

        async def agenerate_structured(self, messages, response_model, **kwargs):
            raise NotImplementedError

        def stream(self, messages, **kwargs):
            yield messages[-1].content

        async def astream(self, messages, **kwargs):
            yield messages[-1].content

    # Register in factory
    LLMProviderFactory.register("echo", CustomEchoProvider)
    assert "echo" in LLMProviderFactory.get_registered_providers()

    # Create via factory
    provider = LLMProviderFactory.create({"provider": "echo", "model": "echo-v1"})
    assert provider.provider_name == "echo"
    res = provider.generate([LLMMessage.user("Ping")])
    assert res.content == "Ping"


def test_retry_mechanism():
    call_counts = {"count": 0}

    class FlakyProvider(MockLLMProvider):
        def generate(self, messages, **kwargs):
            call_counts["count"] += 1
            if call_counts["count"] == 1:
                # First attempt fails with rate limit
                raise LLMRateLimitError("temporary rate limit")
            return super().generate(messages, **kwargs)

    flaky = FlakyProvider(default_response="Recovered!", max_retries=2)
    # execute_with_retry will catch rate limit and retry
    res = flaky.execute_with_retry(lambda: flaky.generate([LLMMessage.user("Hi")]))
    assert res.content == "Recovered!"
    assert call_counts["count"] == 2
