"""Sanitize request/response data before persisting to ConnectionLog (PDPA)."""
from app.core.config import settings

_REDACTED = "[REDACTED]"
_SENSITIVE = {"authorization", "apikey", "api-key", "x-api-key", "cookie"}


def sanitize_body(text: str | None, max_chars: int | None = None) -> str:
    if not text:
        return ""
    limit = max_chars or settings.CONNECTION_LOG_BODY_MAX_CHARS
    if len(text) <= limit:
        return text
    return text[:limit] + "…[truncated]"


def sanitize_headers(headers: dict) -> dict:
    return {k: (_REDACTED if k.lower() in _SENSITIVE else v) for k, v in headers.items()}
