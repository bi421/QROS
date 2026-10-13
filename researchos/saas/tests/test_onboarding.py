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


def test_onboarding_client_uses_canonical_api_error_message_field() -> None:
    client = TestClient(create_app())
    response = client.get("/onboarding/app.js")

    assert response.status_code == 200
    source = response.text
    assert 'data.message || data.detail || "Request failed"' in source
    assert 'data.detail || data.message || "Request failed"' not in source


def test_onboarding_page_exposes_minimal_research_workflow() -> None:
    client = TestClient(create_app())
    response = client.get("/onboarding")
    assert response.status_code == 200
    for expected in (
        'id="dataset-upload"',
        'id="dataset-version"',
        'id="run-research"',
        'id="research-runs"',
        'id="research-detail"',
        "A completed run is not proof of profitability",
    ):
        assert expected in response.text


def test_successful_workspace_provisioning_opens_research_workspace() -> None:
    client = TestClient(create_app())
    response = client.get("/onboarding/app.js")
    assert response.status_code == 200
    source = response.text
    start = source.index("async function finishOnboarding")
    end = source.index("\nfunction showResearchWorkspace", start)
    assert "showResearchWorkspace();" in source[start:end]


def test_onboarding_script_uses_governed_research_api_contract() -> None:
    client = TestClient(create_app())
    response = client.get("/onboarding/app.js")
    assert response.status_code == 200
    for expected in (
        'fetch("/v1/datasets"',
        'qrosApi("/v1/datasets?page=1&page_size=100")',
        'qrosApi("/v1/research-runs"',
        'workflow_id: "xauusd_m1_frozen_research_v1"',
        '"/evidence?page=1&page_size=50"',
        '"/report"',
        'showResearchWorkspace();',
    ):
        assert expected in response.text
