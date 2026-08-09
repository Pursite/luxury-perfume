"""Request-scoped values made available to structured log records."""

from contextvars import ContextVar, Token


request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def bind_request_id(value: str) -> tuple[Token[str | None], Token[str | None]]:
    """Bind an opaque, server-generated identifier for the current request."""
    return request_id.set(value), correlation_id.set(value)


def reset_request_id(tokens: tuple[Token[str | None], Token[str | None]]) -> None:
    """Prevent a request identifier leaking into the next worker request."""
    request_token, correlation_token = tokens
    request_id.reset(request_token)
    correlation_id.reset(correlation_token)


def get_request_id() -> str | None:
    return request_id.get()


def bind_correlation_id(value: str) -> Token[str | None]:
    """Bind a Celery task identifier for log correlation within that task."""
    return correlation_id.set(value)


def reset_correlation_id(token: Token[str | None]) -> None:
    correlation_id.reset(token)


def get_correlation_id() -> str | None:
    return correlation_id.get()
