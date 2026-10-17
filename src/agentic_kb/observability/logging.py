"""Structured and sanitized logging for agentic-kb."""

import json
import logging
import os
import re
import sys
from typing import Any, Dict, Optional

# Regex patterns for masking sensitive information in log streams
SENSITIVE_KEY_PATTERNS = [
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"authorization", re.IGNORECASE),
]

MASK_VALUE = "********"


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively mask sensitive values in dictionaries."""
    sanitized: Dict[str, Any] = {}
    for k, v in data.items():
        if any(pattern.search(str(k)) for pattern in SENSITIVE_KEY_PATTERNS):
            sanitized[k] = MASK_VALUE
        elif isinstance(v, dict):
            sanitized[k] = sanitize_dict(v)
        elif isinstance(v, list):
            sanitized[k] = [
                sanitize_dict(item) if isinstance(item, dict) else item for item in v
            ]
        else:
            sanitized[k] = v
    return sanitized


class StructuredLogFormatter(logging.Formatter):
    """Formats log records as structured text or JSON, omitting sensitive secrets."""

    def __init__(self, json_output: bool = False):
        super().__init__()
        self.json_output = json_output

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include custom contextual attributes if present
        for attr in ("request_id", "trace_id", "tenant_id", "user_id", "duration_ms", "tools_used"):
            val = getattr(record, attr, None)
            if val is not None:
                log_data[attr] = val

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        sanitized = sanitize_dict(log_data)

        if self.json_output:
            return json.dumps(sanitized)
        else:
            extras = ""
            ctx = []
            if "request_id" in sanitized:
                ctx.append(f"req={sanitized['request_id']}")
            if "trace_id" in sanitized:
                ctx.append(f"trace={sanitized['trace_id']}")
            if ctx:
                extras = f" [{' '.join(ctx)}]"
            base = f"[{sanitized['timestamp']}] [{sanitized['level']}]{extras} {sanitized['logger']}: {sanitized['message']}"
            if "exception" in sanitized:
                base += f"\n{sanitized['exception']}"
            return base


def get_logger(name: str = "agentic_kb") -> logging.Logger:
    """Return a logger instance configured for the SDK."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        json_logs = os.getenv("LOG_FORMAT", "text").lower() == "json"
        handler.setFormatter(StructuredLogFormatter(json_output=json_logs))
        logger.addHandler(handler)
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, log_level, logging.INFO))
        logger.propagate = False
    return logger
