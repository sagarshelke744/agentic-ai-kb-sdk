"""Unit tests for the Groq provider (no network)."""

import pytest
from pydantic import BaseModel

from agentic_kb.exceptions.errors import ConfigurationError, LLMRateLimitError
from agentic_kb.llm.factory import LLMProviderFactory
from agentic_kb.llm.groq import GROQ_BASE_URL, GroqProvider, _parse_duration


class _Answer(BaseModel):
    value: int


def test_factory_builds_groq_with_groq_key_and_base_url(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-be-used")
    llm = LLMProviderFactory.create({"provider": "groq", "model": "llama-3.3-70b-versatile"})

    assert isinstance(llm, GroqProvider)
    assert llm.provider_name == "groq"
    assert llm.api_key == "gsk_test"
    assert llm.base_url == GROQ_BASE_URL


def test_factory_honours_custom_gateway_base_url(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    llm = LLMProviderFactory.create(
        {"provider": "groq", "model": "m", "base_url": "https://gateway.example.com/v1"}
    )
    assert llm.base_url == "https://gateway.example.com/v1"


def test_missing_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="GROQ_API_KEY"):
        GroqProvider(api_key=None)._get_client()


@pytest.mark.parametrize(
    "text,expected",
    [("7m12.5s", 432.5), ("1h2m3s", 3723.0), ("2.5s", 2.5), ("850ms", 0.85)],
)
def test_parse_duration(text, expected):
    assert _parse_duration(text) == pytest.approx(expected)


def test_rate_limit_error_carries_retry_after_from_message():
    llm = GroqProvider(api_key="k")
    err = Exception("Error code: 429 - Rate limit reached for model. Please try again in 7m12.5s. Need more tokens?")
    with pytest.raises(LLMRateLimitError) as exc:
        llm._handle_api_error(err)
    assert exc.value.retry_after == pytest.approx(432.5)


def test_structured_output_uses_json_mode_and_parses(monkeypatch):
    llm = GroqProvider(api_key="k")
    captured = {}

    class _Resp:
        content = '```json\n{"value": 42}\n```'
        token_usage = None

    def fake_generate(messages, temperature=None, **kwargs):
        captured.update(kwargs)
        captured["last"] = messages[-1].content
        return _Resp()

    monkeypatch.setattr(llm, "generate", fake_generate)
    result = llm.generate_structured([], _Answer)

    assert result.value == 42
    assert captured["response_format"] == {"type": "json_object"}
    assert "JSON" in captured["last"]
