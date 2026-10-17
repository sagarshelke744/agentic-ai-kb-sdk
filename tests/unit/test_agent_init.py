"""Tests for AgenticKnowledgeBase initialization and lifecycle."""

import pytest
from agentic_kb import AgenticKnowledgeBase, ConfigurationError, MockLLMProvider


def test_agent_init_kwargs():
    agent = AgenticKnowledgeBase(
        llm={"provider": "mock", "model": "test-mock"},
        database={
            "type": "sqlite",
            "host": "localhost",
            "port": 5432,
            "database": "sales_db",
            "username": "ai_user",
        },
        knowledgebase={
            "allowed_tables": ["sales.orders", "sales.products"]
        }
    )
    assert agent.config.agent.name == "database-assistant"
    assert len(agent.config.knowledgebase.allowed_tables) == 2

    health = agent.health_check()
    assert health["status"] == "ok"
    assert health["llm"]["provider"] == "mock"
    assert health["database"]["dialect"] == "sqlite"
    assert health["allowed_tables_count"] == 2


def test_agent_init_from_yaml_with_mock_llm():
    mock_llm = MockLLMProvider(
        responses=[
            '{"requires_database": false, "reasoning": "Direct answer", "relevant_tables": []}',
            "Sales for last month totaled 50,000 USD.",
        ]
    )
    from agentic_kb.database.mock import MockDatabaseProvider
    mock_db = MockDatabaseProvider(database_name="sales_db")
    agent = AgenticKnowledgeBase.from_yaml("configs/example.yaml", llm=mock_llm, db=mock_db)
    assert agent.config.agent.name == "sales-assistant"
    assert agent.llm.provider_name == "mock"

    response = agent.ask("What were total sales last month?")
    assert response.request_id is not None
    assert response.answer == "Sales for last month totaled 50,000 USD."
    assert response.metadata.database_used is False
    assert response.metadata.tokens_used is not None


def test_agent_init_empty_raises():
    with pytest.raises(ConfigurationError):
        AgenticKnowledgeBase()
