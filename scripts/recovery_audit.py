#!/usr/bin/env python3
"""Audit trail with secret redaction for BrandOS autonomous recovery supervisor.

Provides structured JSON logging with automatic redaction of sensitive data
(tokens, API keys, passwords, authorization headers, etc.) for compliance
and debugging of recovery actions.
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# Patterns that indicate sensitive data in keys or values
_SENSITIVE_KEY_PATTERNS = re.compile(
    r"(token|api[_-]?key|password|secret|authorization|auth|credential|bearer|cookie|session)",
    re.IGNORECASE,
)

# Regex patterns for sensitive values
_SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"Basic\s+[A-Za-z0-9+/]+=*", re.IGNORECASE),
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(sk|pk|ak|rk)_[A-Za-z0-9]{8,}"),
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),
    re.compile(r"xoxb-[A-Za-z0-9\-]+"),
    re.compile(r"(?i)\$[A-Z_]*(TOKEN|KEY|PASSWORD|SECRET)[A-Z_]*"),
]

_REDACTED = "[REDACTED]"


class RedactingFilter(logging.Filter):
    """Logging filter that redacts sensitive tokens, keys, passwords, and headers.

    Scans log record messages for patterns matching API keys, Bearer tokens,
    Basic auth, passwords, and environment variable references to secrets.
    Replaces matches with [REDACTED].
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Apply redaction to the log record message.

        Args:
            record: The log record to filter/redact.

        Returns:
            Always True (the record is always emitted, just redacted).
        """
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _REDACTED if self._is_sensitive_key(k) else v
                               for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    _REDACTED if isinstance(a, str) and self._contains_secret(a) else a
                    for a in record.args
                )
        return True

    @staticmethod
    def _redact(text: str) -> str:
        """Redact sensitive patterns from a string.

        Args:
            text: Input string that may contain secrets.

        Returns:
            String with sensitive values replaced by [REDACTED].
        """
        for pattern in _SENSITIVE_VALUE_PATTERNS:
            text = pattern.sub(_REDACTED, text)
        return text

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        """Check if a key name suggests it contains sensitive data.

        Args:
            key: Dictionary key to check.

        Returns:
            True if the key name matches sensitive patterns.
        """
        return bool(_SENSITIVE_KEY_PATTERNS.search(str(key)))

    @staticmethod
    def _contains_secret(value: str) -> bool:
        """Check if a value contains a secret pattern.

        Args:
            value: String value to check.

        Returns:
            True if the value contains a secret pattern.
        """
        return any(p.search(value) for p in _SENSITIVE_VALUE_PATTERNS)


def redact_dict(d: dict) -> dict:
    """Recursively redact sensitive keys from a dictionary.

    Keys matching patterns like 'token', 'api_key', 'password', 'secret',
    'authorization' etc. have their values replaced with [REDACTED].

    Args:
        d: Input dictionary (not modified).

    Returns:
        New dictionary with sensitive values redacted.
    """
    result = {}
    for key, value in d.items():
        if _SENSITIVE_KEY_PATTERNS.search(str(key)):
            result[key] = _REDACTED
        elif isinstance(value, dict):
            result[key] = redact_dict(value)
        elif isinstance(value, list):
            result[key] = [redact_dict(v) if isinstance(v, dict) else v for v in value]
        elif isinstance(value, str):
            # Check if the value itself contains secrets
            redacted = value
            for pattern in _SENSITIVE_VALUE_PATTERNS:
                redacted = pattern.sub(_REDACTED, redacted)
            result[key] = redacted
        else:
            result[key] = value
    return result


class AuditLogger:
    """Structured JSON logger for recovery actions with automatic secret redaction.

    Emits one JSON object per line (NDJSON) to stdout. All entries include
    ISO UTC timestamp, level, and event name. Sensitive data is redacted
    before emission.

    Usage:
        audit = AuditLogger("recovery_supervisor")
        audit.info("startup", version="1.0")
        audit.action("restart_task", task_id="abc123", reason="timed out")
    """

    def __init__(self, name: str = "recovery_audit", stream=None):
        """Initialize the audit logger.

        Args:
            name: Logger name for identification.
            stream: Output stream (defaults to sys.stdout).
        """
        self._name = name
        self._stream = stream or sys.stdout

    def _emit(self, level: str, event: str, **kwargs: Any) -> None:
        """Emit a structured JSON log entry.

        Args:
            level: Log level string (INFO, WARN, ERROR, ACTION).
            event: Event name/description.
            **kwargs: Additional structured fields for the log entry.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            "logger": self._name,
        }
        # Redact kwargs before adding
        redacted = redact_dict(kwargs)
        entry.update(redacted)

        try:
            line = json.dumps(entry, default=str, ensure_ascii=False)
            self._stream.write(line + "\n")
            self._stream.flush()
        except Exception:
            # Fallback: at least try to get the event name out
            self._stream.write(f'{{"level":"{level}","event":"{event}","error":"json_encode_failed"}}\n')
            self._stream.flush()

    def info(self, event: str, **kwargs: Any) -> None:
        """Log an informational event.

        Args:
            event: Event name.
            **kwargs: Additional structured fields.
        """
        self._emit("INFO", event, **kwargs)

    def warn(self, event: str, **kwargs: Any) -> None:
        """Log a warning event.

        Args:
            event: Event name.
            **kwargs: Additional structured fields.
        """
        self._emit("WARN", event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        """Log an error event.

        Args:
            event: Event name.
            **kwargs: Additional structured fields.
        """
        self._emit("ERROR", event, **kwargs)

    def action(self, action_type: str, task_id: str, details: str, **kwargs: Any) -> None:
        """Log a recovery action taken on a task.

        Args:
            action_type: Type of action (e.g. 'restart_task', 'escalate', 'unblock').
            task_id: ID of the task acted upon.
            details: Human-readable description of the action.
            **kwargs: Additional structured fields.
        """
        self._emit(
            "ACTION",
            f"action:{action_type}",
            action_type=action_type,
            task_id=task_id,
            details=details,
            **kwargs,
        )


if __name__ == "__main__":
    # Quick self-test
    audit = AuditLogger("test")
    audit.info("test_event", foo="bar", token="secret123")
    audit.action("restart_task", "task-1", "Timed out after 2h", api_key="sk_test_12345")
    test_dict = {"api_key": "secret", "data": {"password": "hunter2", "name": "test"}}
    print(json.dumps(redact_dict(test_dict), indent=2))
