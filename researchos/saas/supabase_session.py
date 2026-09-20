"""Server-side Supabase session revocation validation."""
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID


class SessionValidationUnavailable(RuntimeError):
    """The authoritative session store could not be checked."""


class SessionValidator(Protocol):
    """Validate that a verified JWT session is still present in Auth."""

    def is_active(self, user_id: UUID, session_id: UUID) -> bool:
        """Return True only when the authoritative Auth session still exists."""


class SupabaseSessionValidator:
    """Validate sessions through the server-only Supabase RPC boundary."""

    def __init__(self, supabase_client: Any) -> None:
        self._client = supabase_client

    def is_active(self, user_id: UUID, session_id: UUID) -> bool:
        try:
            response = self._client.rpc(
                "qros_session_is_active",
                {"p_user_id": str(user_id), "p_session_id": str(session_id)},
            ).execute()
        except Exception as exc:
            raise SessionValidationUnavailable("session validation unavailable") from exc
        return response.data is True


__all__ = ["SessionValidationUnavailable", "SessionValidator", "SupabaseSessionValidator"]
