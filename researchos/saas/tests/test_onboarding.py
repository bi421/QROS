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
