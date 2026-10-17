"""Tests for configuration models and loading."""

import os
import pytest
from pathlib import Path
from agentic_kb.exceptions.errors import ConfigurationError
from agentic_kb.models.config import AgenticKBConfig, DatabaseConfig, LLMConfig


def test_config_from_dict_defaults():
    raw = {
        "database": {
            "type": "postgresql",
            "host": "localhost",
            "port": 5432,
            "database": "test_db",
            "username": "test_user",
        }
    }
    config = AgenticKBConfig.from_dict(raw)
    assert config.agent.name == "database-assistant"
    assert config.database.type == "postgresql"
    assert config.database.database == "test_db"
    assert config.security.read_only is True
    assert config.security.max_rows == 1000
    assert config.llm.provider == "openai"


def test_config_from_yaml():
    yaml_path = Path("configs/example.yaml")
    config = AgenticKBConfig.from_yaml(yaml_path)
    assert config.agent.name == "sales-assistant"
    assert "sales.orders" in config.knowledgebase.allowed_tables
    assert config.security.read_only is True
    assert config.database.port == 5432


def test_env_var_expansion(monkeypatch):
    monkeypatch.setenv("TEST_DB_HOST", "db.internal.net")
    monkeypatch.setenv("TEST_DB_PORT", "5433")
    monkeypatch.setenv("TEST_OPENAI_KEY", "sk-secret-test-key")

    raw = {
        "llm": {
            "api_key": "${TEST_OPENAI_KEY}",
        },
        "database": {
            "type": "postgresql",
            "host": "${TEST_DB_HOST}",
            "port": 5432,
            "database": "sales_db",
            "username": "user",
        },
    }
    config = AgenticKBConfig.from_dict(raw)
    assert config.database.host == "db.internal.net"
    assert config.llm.api_key == "sk-secret-test-key"


def test_default_env_var_fallback():
    raw = {
        "database": {
            "type": "postgresql",
            "host": "${NON_EXISTENT_VAR:-fallback.host.com}",
            "port": 5432,
            "database": "sales_db",
            "username": "user",
        }
    }
    config = AgenticKBConfig.from_dict(raw)
    assert config.database.host == "fallback.host.com"


def test_invalid_port_validation():
    with pytest.raises(ConfigurationError):
        AgenticKBConfig.from_dict({
            "database": {
                "type": "postgresql",
                "host": "localhost",
                "port": 999999,  # invalid port
                "database": "sales_db",
                "username": "user",
            }
        })


def test_missing_required_fields():
    with pytest.raises(ConfigurationError):
        AgenticKBConfig.from_dict({})
