"""Prompt injection detection and sensitive data masking sanitizer."""

import re
from typing import Any, Dict, List, Optional
from agentic_kb.exceptions.errors import PromptInjectionError
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.security.sanitizer")

# Patterns indicating prompt injection or jailbreak attempts
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+dan\s+mode", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+prompt|instructions|api\s+keys?)", re.IGNORECASE),
    re.compile(r"show\s+me\s+(all\s+)?passwords?", re.IGNORECASE),
    re.compile(r"bypass\s+(security|safety|guardrails)", re.IGNORECASE),
    re.compile(r"do\s+anything\s+now", re.IGNORECASE),
]

# Sensitive PII patterns
CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")


class InputSanitizer:
    """Detects prompt injection attacks and sanitizes user requests."""

    @classmethod
    def check_prompt_injection(cls, user_text: str) -> Optional[str]:
        """Return pattern description if prompt injection is suspected, None otherwise."""
        for pattern in INJECTION_PATTERNS:
            match = pattern.search(user_text)
            if match:
                return f"Matched suspicious pattern '{match.group(0)}'"
        return None

    @classmethod
    def validate_input(cls, user_text: str) -> str:
        """Validate input text; raises PromptInjectionError if injection detected."""
        reason = cls.check_prompt_injection(user_text)
        if reason:
            logger.warning(f"Blocked potential prompt injection: {reason}")
            raise PromptInjectionError(reason=reason)
        return user_text.strip()


class DataMasker:
    """Masks sensitive personal and credential information in text and results."""

    @classmethod
    def mask_text(cls, text: str) -> str:
        """Mask credit cards and SSNs in plain text."""
        masked = CREDIT_CARD_PATTERN.sub("[MASKED_CARD]", text)
        masked = SSN_PATTERN.sub("[MASKED_SSN]", masked)
        return masked

    @classmethod
    def mask_record(cls, record: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive column values in database rows."""
        masked: Dict[str, Any] = {}
        sensitive_col_keys = {"password", "secret", "token", "ssn", "cvv", "credit_card", "api_key"}

        for k, v in record.items():
            if any(s in str(k).lower() for s in sensitive_col_keys):
                masked[k] = "********"
            elif isinstance(v, str):
                masked[k] = cls.mask_text(v)
            else:
                masked[k] = v
        return masked
