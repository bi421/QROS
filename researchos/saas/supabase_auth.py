"""Supabase JWT authentication adapter.

The adapter verifies the bearer token with Supabase Auth, optionally enforces
an authoritative session-revocation check, and then delegates workspace
authorization to a separate membership resolver. Authorization is never
inferred from user-editable profile metadata.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from fastapi import HTTPException, status

from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole
from researchos.saas.supabase_session import SessionValidationUnavailable, SessionValidator


class WorkspaceMembershipResolver(Protocol):
    """Resolve the caller's authorized workspace, role, and server-side plan."""

    def resolve(
        self,
        user_id: UUID,
        requested_workspace_id: UUID | None = None,
    ) -> tuple[UUID, Plan, WorkspaceRole] | None:
        """Return one authorized workspace/role/plan or None if unauthorized."""


class SupabaseJwtAuthProvider:
    """Fail-closed Supabase JWT verifier for FastAPI Authorization headers."""

    def __init__(
        self,
        supabase_client: Any,
        membership_resolver: WorkspaceMembershipResolver,
        expected_issuer: str = "",
        session_validator: SessionValidator | None = None,
    ) -> None:
        self._client = supabase_client
        self._membership = membership_resolver
        self._expected_issuer = expected_issuer.rstrip("/")
        self._session_validator = session_validator

    def authenticate(self, authorization: str | None, requested_workspace_id: UUID | None = None) -> TenantContext:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")

        token = authorization[7:].strip()
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")

        try:
            response = self._client.auth.get_claims(token)
            claims = response.get("claims") if isinstance(response, dict) else None
            if not isinstance(claims, dict):
                raise ValueError("missing verified claims")
            if claims.get("role") != "authenticated":
                raise ValueError("invalid authentication role")
            audience = claims.get("aud")
            if audience != "authenticated" and not (
                isinstance(audience, list) and "authenticated" in audience
            ):
                raise ValueError("invalid authentication audience")
            if self._expected_issuer and claims.get("iss") != self._expected_issuer:
                raise ValueError("invalid authentication issuer")
            user_id = UUID(str(claims.get("sub", "")))
            session_id = UUID(str(claims.get("session_id", "")))
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid authentication token",
            ) from exc

        if self._session_validator is not None:
            try:
                session_active = self._session_validator.is_active(user_id, session_id)
            except SessionValidationUnavailable as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="authentication session state is unavailable",
                ) from exc
            if not session_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="authentication session is no longer active",
                )

        try:
            resolved = self._membership.resolve(user_id, requested_workspace_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="workspace entitlement state is unavailable",
            ) from exc
        if resolved is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="workspace access denied")

        workspace_id, plan, role = resolved
        return TenantContext(user_id=user_id, workspace_id=workspace_id, plan=plan, role=role)


__all__ = ["SupabaseJwtAuthProvider", "WorkspaceMembershipResolver"]
