"""Stable API error contract for the ResearchOS SaaS boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SaaSError:
    """Machine-readable error details that are safe to expose to clients."""

    code: str
    message: str
    status_code: int

    def body(self, request_id: str) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "request_id": request_id,
            }
        }


BAD_REQUEST = SaaSError("bad_request", "request could not be processed", 400)
UNAUTHORIZED = SaaSError("unauthorized", "authentication is required", 401)
FORBIDDEN = SaaSError("forbidden", "access denied", 403)
NOT_FOUND = SaaSError("not_found", "resource not found", 404)
CONFLICT = SaaSError("conflict", "resource state conflicts with the request", 409)
RATE_LIMITED = SaaSError("rate_limited", "request rate limit exceeded", 429)
INTERNAL_ERROR = SaaSError("internal_error", "internal server error", 500)
SERVICE_UNAVAILABLE = SaaSError("service_unavailable", "service is temporarily unavailable", 503)


__all__ = [
    "BAD_REQUEST",
    "CONFLICT",
    "FORBIDDEN",
    "INTERNAL_ERROR",
    "NOT_FOUND",
    "RATE_LIMITED",
    "SERVICE_UNAVAILABLE",
    "SaaSError",
    "UNAUTHORIZED",
]
