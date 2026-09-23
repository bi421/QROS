from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from researchos.saas.api import create_app
from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole


class StaticAuth:
    def authenticate(self, authorization: str | None, requested_workspace_id=None) -> TenantContext:
        return TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.OWNER)


def test_public_v1_contract_routes_are_present() -> None:
    app = create_app(auth_provider=StaticAuth())
    paths = set(app.openapi()["paths"])
    expected = {
        "/v1/me",
        "/v1/datasets",
        "/v1/datasets/{dataset_id}/versions",
        "/v1/datasets/{dataset_id}/versions/{version_id}/download",
        "/v1/research-runs",
        "/v1/research-runs/{job_id}",
        "/v1/research-runs/{job_id}/logs",
        "/v1/research-runs/{job_id}/result",
        "/v1/research-runs/{job_id}/evidence",
        "/v1/research-runs/{job_id}/report",
        "/v1/research-claims",
        "/v1/research-claims/{claim_id}",
        "/v1/research-claims/{claim_id}/evidence-graph",
    }
    assert expected <= paths


def test_errors_have_structured_metadata_and_request_id_header() -> None:
    app = create_app(auth_provider=StaticAuth())
    response = TestClient(app).get(f"/v1/research-runs/{uuid4()}")
    assert response.status_code == 404
    assert response.headers["X-Request-ID"]
    body = response.json()
    assert set(body) == {"code", "message", "request_id", "correlation_id"}
    assert body["code"] == "not_found"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["correlation_id"] == response.headers["X-Request-ID"]


def test_openapi_documents_error_schema_and_request_id() -> None:
    app = create_app(auth_provider=StaticAuth())
    schema = app.openapi()
    error_schema = schema["components"]["schemas"]["ErrorResponse"]
    assert error_schema["required"] == ["code", "message", "request_id", "correlation_id"]
    operation = schema["paths"]["/v1/research-runs/{job_id}"]["get"]
    response = operation["responses"]["404"]
    assert response["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ErrorResponse"
    assert "X-Request-ID" in response["headers"]
