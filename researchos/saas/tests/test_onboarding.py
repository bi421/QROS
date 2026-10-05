from fastapi.testclient import TestClient

from researchos.saas.api import create_app


def test_onboarding_page_is_public_and_uses_same_origin_api() -> None:
    client = TestClient(
        create_app(
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="public-key",
        )
    )
    response = client.get("/onboarding")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/onboarding/app.js" in response.text
    assert "SUPABASE_SERVICE_ROLE_KEY" not in response.text


def test_onboarding_script_contains_supported_customer_handoff() -> None:
    client = TestClient(
        create_app(
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="public-key",
        )
    )
    response = client.get("/onboarding/app.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    for expected in (
        '"/signup"',
        '"/token?grant_type=password"',
        '"/v1/workspaces"',
        '"/v1/me"',
        'headers.Authorization',
    ):
        assert expected in response.text


def test_onboarding_config_fails_closed_when_publishable_key_is_missing() -> None:
    client = TestClient(create_app(supabase_url="https://example.supabase.co"))
    response = client.get("/onboarding/config")
    assert response.status_code == 503


def test_onboarding_config_exposes_only_public_auth_configuration() -> None:
    client = TestClient(
        create_app(
            supabase_url="https://example.supabase.co/",
            supabase_publishable_key="public-key",
        )
    )
    response = client.get("/onboarding/config")
    assert response.status_code == 200
    assert response.json() == {
        "supabase_url": "https://example.supabase.co",
        "supabase_publishable_key": "public-key",
    }


def test_workspace_provisioning_requires_verified_user_and_returns_free_owner() -> None:
    from uuid import UUID, uuid4

    from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole
    from researchos.saas.workspace import WorkspaceProvisioningResult

    user_id = uuid4()

    class Auth:
        def authenticate_user(self, authorization: str | None) -> UUID:
            assert authorization == "Bearer test"
            return user_id

        def authenticate(self, authorization: str | None) -> TenantContext:
            assert authorization == "Bearer test"
            return TenantContext(user_id, uuid4(), Plan.FREE, WorkspaceRole.OWNER)

    class Provisioner:
        def __init__(self) -> None:
            self.calls: list[tuple[UUID, str]] = []

        def provision(self, caller_id: UUID, name: str) -> WorkspaceProvisioningResult:
            self.calls.append((caller_id, name))
            return WorkspaceProvisioningResult(uuid4(), WorkspaceRole.OWNER, Plan.FREE)

    provisioner = Provisioner()
    client = TestClient(create_app(auth_provider=Auth(), workspace_provisioner=provisioner))
    response = client.post(
        "/v1/workspaces",
        headers={"Authorization": "Bearer test"},
        json={"name": "My QROS Workspace"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert UUID(payload["workspace_id"])
    assert payload["role"] == "owner"
    assert payload["plan"] == "free"
    assert provisioner.calls == [(user_id, "My QROS Workspace")]


def test_onboarding_client_uses_canonical_api_error_message_field() -> None:
    client = TestClient(create_app())
    response = client.get("/onboarding/app.js")

    assert response.status_code == 200
    source = response.text
    assert 'data.message || data.detail || "Request failed"' in source
    assert 'data.detail || data.message || "Request failed"' not in source
