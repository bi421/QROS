from uuid import uuid4

from researchos.saas.contracts import Plan
from researchos.saas.supabase_auth import SupabaseJwtAuthProvider
from researchos.saas.supabase_membership import SupabaseWorkspaceMembershipResolver


class ClaimsAuth:
    class _Auth:
        def get_claims(self, token):
            assert token == "good"
            return {"claims": {"sub": str(USER_ID)}}

    auth = _Auth()


class Membership:
    def resolve(self, user_id):
        assert user_id == USER_ID
        return WORKSPACE_ID, Plan.PRO


USER_ID = uuid4()
WORKSPACE_ID = uuid4()


def test_supabase_auth_adapter_maps_verified_claims_to_tenant() -> None:
    context = SupabaseJwtAuthProvider(ClaimsAuth(), Membership()).authenticate("Bearer good")
    assert context.user_id == USER_ID
    assert context.workspace_id == WORKSPACE_ID
    assert context.plan is Plan.PRO


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
            return Query([{"workspace_id": str(WORKSPACE_ID)}])
        return Query([{"plan": "team", "status": "active"}])


def test_supabase_membership_resolver_uses_server_subscription_state() -> None:
    result = SupabaseWorkspaceMembershipResolver(Client()).resolve(USER_ID)
    assert result == (WORKSPACE_ID, Plan.TEAM)
