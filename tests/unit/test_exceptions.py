"""Tests for error hierarchy and user-safe error messages."""

from agentic_kb.exceptions.errors import (
    AgenticKBError,
    DatabaseTimeoutError,
    PermissionDeniedError,
    SQLValidationError,
)


def test_sql_validation_error_user_safe():
    err = SQLValidationError("SELECT * FROM passwords contains forbidden table", sql="SELECT * FROM passwords")
    assert "blocked" in err.user_safe_message.lower()
    # SQL should be in internal details or attribute, but user-safe message should not reveal it
    assert "passwords" not in err.user_safe_message


def test_permission_denied_error():
    err = PermissionDeniedError("hr.salaries")
    assert "hr.salaries" in err.message
    d = err.to_dict()
    assert d["error_type"] == "PermissionDeniedError"
    assert "permission" in d["user_safe_message"].lower()


def test_database_timeout_error():
    err = DatabaseTimeoutError(30.0)
    assert "timed out" in err.user_safe_message.lower()
    assert err.details["timeout_seconds"] == 30.0
