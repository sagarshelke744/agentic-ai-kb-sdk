"""Tests for structured and sensitive-data masked logging."""

from agentic_kb.observability.logging import sanitize_dict, get_logger


def test_sanitize_dict_masks_secrets():
    payload = {
        "db_password": "supersecretpassword",
        "api_key": "sk-1234567890",
        "token": "bearer xyz",
        "normal_field": "public_data",
        "nested": {
            "auth_secret": "my-secret-key",
            "username": "admin",
        },
    }
    sanitized = sanitize_dict(payload)
    assert sanitized["db_password"] == "********"
    assert sanitized["api_key"] == "********"
    assert sanitized["token"] == "********"
    assert sanitized["normal_field"] == "public_data"
    assert sanitized["nested"]["auth_secret"] == "********"
    assert sanitized["nested"]["username"] == "admin"


def test_get_logger():
    logger = get_logger("test_logger")
    assert logger.name == "test_logger"
