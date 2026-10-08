"""Typed application errors and their HTTP mapping for message_pusher.

Every error carries a stable machine-readable code so callers, dashboards and
alert rules never have to parse an English sentence.
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "AppError",
    "BadRequest",
    "NotFound",
    "Conflict",
    "Unauthorized",
    "Forbidden",
    "PayloadTooLarge",
    "RateLimited",
    "ServiceUnavailable",
    "error_payload",
]


class AppError(Exception):
    """Base class for errors that are safe to show to a caller."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str | None = None, **context: Any) -> None:
        self.message = message or self.__class__.__doc__ or self.code
        self.context: dict[str, Any] = dict(context)
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": self.code, "message": self.message}
        if self.context:
            payload["details"] = self.context
        return payload

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"{self.__class__.__name__}({self.message!r}, {self.context!r})"


class BadRequest(AppError):
    """The request could not be understood."""

    status_code = 400
    code = "bad_request"


class Unauthorized(AppError):
    """Authentication is required."""

    status_code = 401
    code = "unauthorized"


class Forbidden(AppError):
    """The caller is authenticated but not allowed."""

    status_code = 403
    code = "forbidden"


class NotFound(AppError):
    """The requested resource does not exist."""

    status_code = 404
    code = "not_found"


class Conflict(AppError):
    """The request conflicts with the current state."""

    status_code = 409
    code = "conflict"


class PayloadTooLarge(AppError):
    """The request body exceeds the configured limit."""

    status_code = 413
    code = "payload_too_large"


class RateLimited(AppError):
    """The caller exceeded its quota."""

    status_code = 429
    code = "rate_limited"


class ServiceUnavailable(AppError):
    """A dependency the request needs is not reachable."""

    status_code = 503
    code = "service_unavailable"


def error_payload(code: str, message: str, **details: Any) -> dict[str, Any]:
    """Build the canonical error envelope for hand-rolled responses."""
    payload: dict[str, Any] = {"error": code, "message": message}
    if details:
        payload["details"] = details
    return payload
