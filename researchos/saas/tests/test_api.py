from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from researchos.research_core.contracts import FROZEN_XAUUSD_M1_WORKFLOW
from researchos.saas.api import create_app
from researchos.saas.config import SaaSSettings
from researchos.saas.contracts import Plan, TenantContext
from researchos.saas.store import InMemoryResearchJobStore


class StaticAuth:
    def __init__(self, context: TenantContext) -> None:
        self.context = context

    def authenticate(self, authorization: str | None) -> TenantContext:
        assert authorization == "Bearer test"
        return self.context


def _client(workspace_id: UUID | None = None) -> TestClient:
    context = TenantContext(
        user_id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        plan=Plan.PRO,
    )
    return TestClient(
        create_app(
            auth_provider=StaticAuth(context),
            job_store=InMemoryResearchJobStore(),
        )
    )


def _production_settings() -> SaaSSettings:
    return SaaSSettings(
        environment="production",
        service_name="researchos-saas",
        log_level="INFO",
        auth_required=True,
        request_timeout_seconds=60,
        max_request_body_bytes=10_000_000,
        request_id_max_length=128,
        rate_limit_per_minute=60,
        supabase_url="https://example.supabase.co",
        supabase_publishable_key=None,
        supabase_service_role_key="server-secret",
    )


def test_health_does_not_require_authentication() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(response.headers["X-Request-ID"]) == 36


def test_security_headers_are_present() -> None:
    response = TestClient(create_app()).get("/healthz")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["Cache-Control"] == "no-store"


def test_production_does_not_expose_interactive_api_docs() -> None:
    client = TestClient(create_app(settings=_production_settings()))

    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_request_id_is_propagated_and_bounded() -> None:
    client = TestClient(create_app())
    supplied = "request-123"
    response = client.get("/healthz", headers={"X-Request-ID": supplied})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == supplied

    long_id = "x" * 256
    response = client.get("/healthz", headers={"X-Request-ID": long_id})
    assert response.status_code == 200
    assert len(response.headers["X-Request-ID"]) == 128


def test_readiness_does_not_require_authentication() -> None:
    client = TestClient(create_app())
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_unconfigured_saas_auth_fails_closed() -> None:
    client = TestClient(create_app())
    response = client.get("/v1/me", headers={"Authorization": "Bearer anything"})
    assert response.status_code == 503


def test_create_and_get_research_job_are_tenant_scoped() -> None:
    workspace_id = uuid4()
    client = _client(workspace_id)
    response = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test"},
        json={"dataset_id": "xauusd-m1-2021-2025"},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["workspace_id"] == str(workspace_id)
    assert payload["status"] == "queued"
    assert payload["workflow_id"] == FROZEN_XAUUSD_M1_WORKFLOW

    job_id = payload["id"]
    fetched = client.get(
        f"/v1/research-runs/{job_id}",
        headers={"Authorization": "Bearer test"},
    )
    assert fetched.status_code == 200
    assert fetched.json()["id"] == job_id


def test_unsupported_workflow_is_rejected() -> None:
    client = _client()
    response = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test"},
        json={"dataset_id": "xauusd-m1", "workflow_id": "arbitrary"},
    )
    assert response.status_code == 400


def test_cross_tenant_job_lookup_returns_404() -> None:
    store = InMemoryResearchJobStore()
    owner = TenantContext(uuid4(), uuid4(), Plan.PRO)
    other = TenantContext(uuid4(), uuid4(), Plan.PRO)
    owner_client = TestClient(create_app(auth_provider=StaticAuth(owner), job_store=store))
    other_client = TestClient(create_app(auth_provider=StaticAuth(other), job_store=store))

    created = owner_client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test"},
        json={"dataset_id": "xauusd-m1"},
    )
    job_id = created.json()["id"]

    response = other_client.get(
        f"/v1/research-runs/{job_id}",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 404
