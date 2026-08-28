"""Safe structured logging primitives for containerized application processes."""

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from apps.lib.log_context import get_correlation_id, get_request_id


_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(password|otp|token|jwt|secret|credential|authorization|api_key|"
    r"merchant_secret|webhook_signature|provider_session|pan|card|cvv|cvc|pin)\b"
    r"\s*([=:])\s*[^\s,|&]+"
)
_PHONE_NUMBER = re.compile(r"\b09\d{9}\b")
_EMAIL_ADDRESS = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_JWT = re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+\b")


def sanitize_log_value(value: Any) -> str:
    """Redact common secret and PII patterns before they reach a log sink."""
    sanitized = str(value)
    sanitized = _SENSITIVE_ASSIGNMENT.sub(r"\1\2[redacted]", sanitized)
    sanitized = _JWT.sub("[redacted-jwt]", sanitized)
    sanitized = _PHONE_NUMBER.sub("[redacted-phone]", sanitized)
    return _EMAIL_ADDRESS.sub("[redacted-email]", sanitized)


class RequestContextFilter(logging.Filter):
    """Attach the request identifier to records without accepting request data."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        record.correlation_id = get_correlation_id()
        if record.name.startswith("django.security"):
            record.category = "security"
            record.event = "django.security.warning"
        elif record.name.startswith("django"):
            record.category = "system"
            record.event = "django.error"
        return True


class JsonFormatter(logging.Formatter):
    """Emit a small, allowlisted JSON record suitable for Docker log drivers."""

    _safe_extra_fields = ("category", "user_id", "path", "task_id")

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", record.getMessage())
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "category": getattr(record, "category", record.name),
            "event": sanitize_log_value(event),
        }

        request_id = getattr(record, "request_id", get_request_id())
        if request_id:
            payload["request_id"] = request_id

        correlation_id = getattr(record, "correlation_id", get_correlation_id())
        if correlation_id:
            payload["correlation_id"] = correlation_id

        for field in self._safe_extra_fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = (
                    value if field == "user_id" else sanitize_log_value(value)
                )

        if record.exc_info and record.exc_info[0]:
            payload["exception_type"] = record.exc_info[0].__name__

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
