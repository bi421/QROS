from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import HTTPException

from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole
from researchos.saas.supabase_auth import SupabaseJwtAuthProvider
from researchos.saas.supabase_session import SessionValidationUnavailable


USER_ID = UUID("00000000-0000-0000-0000-000000000001")
SESSION_ID = UUID("00000000-0000-0000-0000-000000000002")
WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000003")


class FakeAuth:
    def __init__(self, claims: dict[str, object]) -> None:
        self.claims = claims

    def get_claims(self, token: str) -> dict[str, object]:
        return {"claims": self.claims}


class FakeClient:
    def __init__(self, claims: dict[str, object]) -> None:
        self.auth = FakeAuth(claims)


class FakeMembership:
    def resolve(self, user_id: UUID, requested_workspace_id: UUID | None = None):
        assert user_id == USER_ID
        return WORKSPACE_ID, Plan.FREE, WorkspaceRole.VIEWER


class FakeSessionValidator:
    def __init__(self, result: bool | Exception) -> None:
        self.result = result
        self.calls: list[tuple[UUID, UUID]] = []

    def is_active(self, user_id: UUID, session_id: UUID) -> bool:
        self.calls.append((user_id, session_id))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def claims() -> dict[str, object]:
    return {
        "role": "authenticated",
        "aud": "authenticated",
        "iss": "https://example.supabase.co/auth/v1",
        "sub": str(USER_ID),
        "session_id": str(SESSION_ID),
    }


def provider(validator: FakeSessionValidator) -> SupabaseJwtAuthProvider:
    return SupabaseJwtAuthProvider(
        FakeClient(claims()),
        FakeMembership(),
        expected_issuer="https://example.supabase.co/auth/v1",
        session_validator=validator,
    )


def test_active_session_is_required_before_workspace_resolution() -> None:
    validator = FakeSessionValidator(True)
    result = provider(validator).authenticate("Bearer token")

    assert result == TenantContext(
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
        plan=Plan.FREE,
        role=WorkspaceRole.VIEWER,
    )
    assert validator.calls == [(USER_ID, SESSION_ID)]


def test_revoked_session_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        provider(FakeSessionValidator(False)).authenticate("Bearer token")

    assert exc.value.status_code == 401
    assert exc.value.detail == "authentication session is no longer active"


def test_session_validation_outage_fails_closed() -> None:
    with pytest.raises(HTTPException) as exc:
        provider(FakeSessionValidator(SessionValidationUnavailable())).authenticate("Bearer token")

    assert exc.value.status_code == 503
    assert exc.value.detail == "authentication session state is unavailable"
