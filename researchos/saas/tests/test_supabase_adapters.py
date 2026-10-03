from uuid import uuid4

from researchos.saas.contracts import Plan, WorkspaceRole
from researchos.saas.supabase_auth import SupabaseJwtAuthProvider
from researchos.saas.supabase_membership import SupabaseWorkspaceMembershipResolver


class ClaimsAuth:
    class _Auth:
        def get_claims(self, token):
            assert token == "good"
            return {"claims": {"sub": str(USER_ID), "role": "authenticated", "aud": "authenticated", "iss": EXPECTED_ISSUER, "session_id": str(SESSION_ID)}}

    auth = _Auth()


class Membership:
    def resolve(self, user_id, requested_workspace_id=None):
        assert user_id == USER_ID
        assert requested_workspace_id in (None, WORKSPACE_ID)
        return WORKSPACE_ID, Plan.PRO, WorkspaceRole.RESEARCHER


USER_ID = uuid4()
WORKSPACE_ID = uuid4()
SESSION_ID = uuid4()
EXPECTED_ISSUER = "https://pvhdsngxyoiqhqwujfjt.supabase.co/auth/v1"


def test_supabase_auth_adapter_maps_verified_claims_to_tenant() -> None:
    context = SupabaseJwtAuthProvider(ClaimsAuth(), Membership()).authenticate("Bearer good")
    assert context.user_id == USER_ID
    assert context.workspace_id == WORKSPACE_ID
    assert context.plan is Plan.PRO
    assert context.role is WorkspaceRole.RESEARCHER


class Query:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        return type("Response", (), {"data": self.rows})()


class Client:
    def table(self, name):
        if name == "workspace_member":
            return Query([{"workspace_id": str(WORKSPACE_ID), "user_id": str(USER_ID), "role": "researcher"}])
        return Query([{"plan": "team", "status": "active"}])


def test_supabase_membership_resolver_uses_server_subscription_state() -> None:
    result = SupabaseWorkspaceMembershipResolver(Client()).resolve(USER_ID)
    assert result == (WORKSPACE_ID, Plan.TEAM, WorkspaceRole.RESEARCHER)


class MultiWorkspaceClient(Client):
    def table(self, name):
        if name == "workspace_member":
            return Query([
                {"workspace_id": str(WORKSPACE_ID), "role": "researcher"},
                {"workspace_id": str(uuid4()), "role": "viewer"},
            ])
        return Query([{"plan": "team", "status": "active"}])


def test_duplicate_workspace_membership_fails_closed() -> None:
    import pytest

    class DuplicateMembershipClient(Client):
        def table(self, name):
            if name == "workspace_member":
                return Query([
                    {"workspace_id": str(WORKSPACE_ID), "role": "researcher"},
                    {"workspace_id": str(WORKSPACE_ID), "role": "admin"},
                ])
            return Query([{"plan": "team", "status": "active"}])

    with pytest.raises(RuntimeError, match="duplicate workspace membership"):
        SupabaseWorkspaceMembershipResolver(DuplicateMembershipClient()).resolve(USER_ID)


def test_multi_workspace_resolution_requires_explicit_selection() -> None:
    import pytest

    with pytest.raises(ValueError, match="workspace selection is required"):
        SupabaseWorkspaceMembershipResolver(MultiWorkspaceClient()).resolve(USER_ID)


def test_multi_workspace_resolution_accepts_authorized_workspace() -> None:
    other_workspace = uuid4()
    class SelectedClient(Client):
        def table(self, name):
            if name == "workspace_member":
                return Query([
                    {"workspace_id": str(WORKSPACE_ID), "role": "admin"},
                    {"workspace_id": str(other_workspace), "role": "viewer"},
                ])
            return Query([{"plan": "team", "status": "active"}])

    assert SupabaseWorkspaceMembershipResolver(SelectedClient()).resolve(
        USER_ID, WORKSPACE_ID
    ) == (WORKSPACE_ID, Plan.TEAM, WorkspaceRole.ADMIN)


class BrokenMembership:
    def resolve(self, user_id, requested_workspace_id=None):
        raise RuntimeError("invalid active subscription entitlement")


def test_supabase_auth_maps_entitlement_corruption_to_service_unavailable() -> None:
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        SupabaseJwtAuthProvider(ClaimsAuth(), BrokenMembership()).authenticate("Bearer good")
    assert exc_info.value.status_code == 503


def test_membership_resolver_returns_server_role() -> None:
    class ViewerClient(Client):
        def table(self, name):
            if name == "workspace_member":
                return Query([{"workspace_id": str(WORKSPACE_ID), "role": "viewer"}])
            return Query([{"plan": "team", "status": "active"}])

    assert SupabaseWorkspaceMembershipResolver(ViewerClient()).resolve(USER_ID) == (
        WORKSPACE_ID, Plan.TEAM, WorkspaceRole.VIEWER
    )


def test_malformed_membership_role_fails_closed() -> None:
    class BrokenRoleClient(Client):
        def table(self, name):
            if name == "workspace_member":
                return Query([{"workspace_id": str(WORKSPACE_ID), "role": "superuser"}])
            return Query([{"plan": "team", "status": "active"}])

    import pytest
    with pytest.raises(RuntimeError, match="invalid workspace membership role"):
        SupabaseWorkspaceMembershipResolver(BrokenRoleClient()).resolve(USER_ID)


def test_supabase_auth_rejects_missing_or_malformed_bearer_token() -> None:
    import pytest
    from fastapi import HTTPException

    provider = SupabaseJwtAuthProvider(ClaimsAuth(), Membership())

    for authorization in (None, "", "Basic good", "Bearer "):
        with pytest.raises(HTTPException) as exc_info:
            provider.authenticate(authorization)
        assert exc_info.value.status_code == 401


def test_supabase_auth_rejects_invalid_or_missing_subject_claim() -> None:
    import pytest
    from fastapi import HTTPException

    class BrokenClaimsAuth:
        class _Auth:
            def get_claims(self, token):
                if token == "missing-sub":
                    return {"claims": {}}
                return {"claims": {"sub": "not-a-uuid"}}

        auth = _Auth()

    provider = SupabaseJwtAuthProvider(BrokenClaimsAuth(), Membership())

    for token in ("missing-sub", "bad-sub"):
        with pytest.raises(HTTPException) as exc_info:
            provider.authenticate(f"Bearer {token}")
        assert exc_info.value.status_code == 401


def test_supabase_auth_rejects_unexpected_claims_provider_failure() -> None:
    import pytest
    from fastapi import HTTPException

    class FailingClaimsAuth:
        class _Auth:
            def get_claims(self, token):
                raise RuntimeError("verification failed")

        auth = _Auth()

    with pytest.raises(HTTPException) as exc_info:
        SupabaseJwtAuthProvider(FailingClaimsAuth(), Membership()).authenticate("Bearer bad")
    assert exc_info.value.status_code == 401


def test_subscription_resolution_ignores_inactive_history_and_uses_active_entitlement() -> None:
    class HistoricalSubscriptionClient(Client):
        def table(self, name):
            if name == "workspace_member":
                return Query([{"workspace_id": str(WORKSPACE_ID), "role": "researcher"}])
            return Query([
                {"plan": "free", "status": "canceled"},
                {"plan": "team", "status": "active"},
            ])

    assert SupabaseWorkspaceMembershipResolver(HistoricalSubscriptionClient()).resolve(USER_ID) == (
        WORKSPACE_ID, Plan.TEAM, WorkspaceRole.RESEARCHER
    )


def test_duplicate_active_subscriptions_fail_closed() -> None:
    import pytest

    class DuplicateSubscriptionClient(Client):
        def table(self, name):
            if name == "workspace_member":
                return Query([{"workspace_id": str(WORKSPACE_ID), "role": "researcher"}])
            return Query([
                {"plan": "team", "status": "active"},
                {"plan": "pro", "status": "active"},
            ])

    with pytest.raises(RuntimeError, match="ambiguous active subscription entitlement"):
        SupabaseWorkspaceMembershipResolver(DuplicateSubscriptionClient()).resolve(USER_ID)
