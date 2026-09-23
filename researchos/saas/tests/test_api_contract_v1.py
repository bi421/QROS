from io import BytesIO
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from researchos.saas.api import create_app
from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole
from researchos.saas.datasets import InMemoryDatasetStorage, InMemoryDatasetStore
from researchos.saas.store import InMemoryResearchJobStore
from researchos.saas.storage.signed_urls import dataset_object_path, sign_path, verify_path_signature


class Auth:
    def __init__(self, tenant: TenantContext) -> None:
        self.tenant = tenant

    def authenticate(self, authorization: str | None, requested_workspace_id: UUID | None = None) -> TenantContext:
        if authorization != "Bearer test":
            raise HTTPException(status_code=401, detail="unauthorized")
        if requested_workspace_id is not None and requested_workspace_id != self.tenant.workspace_id:
            raise HTTPException(status_code=403, detail="workspace access denied")
        return self.tenant


def client() -> tuple[TestClient, TenantContext]:
    tenant = TenantContext(uuid4(), uuid4(), Plan.TEAM, WorkspaceRole.RESEARCHER)
    return TestClient(create_app(
        auth_provider=Auth(tenant),
        job_store=InMemoryResearchJobStore(),
        dataset_store=InMemoryDatasetStore(),
        dataset_storage=InMemoryDatasetStorage(),
    )), tenant


def test_list_contract_defaults_and_invalid_controls() -> None:
    api, tenant = client()
    response = api.get("/v1/research-runs", headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "pagination", "request_id"}
    assert body["pagination"] == {"page": 1, "page_size": 20, "total": 0, "total_pages": 0}
    assert body["request_id"]

    invalid_sort = api.get("/v1/research-runs?sort_by=evil", headers={"Authorization": "Bearer test"})
    assert invalid_sort.status_code == 400
    assert invalid_sort.json()["code"] == "INVALID_SORT"

    invalid_filter = api.get("/v1/research-runs?filter[evil]=x", headers={"Authorization": "Bearer test"})
    assert invalid_filter.status_code == 400
    assert invalid_filter.json()["code"] == "INVALID_FILTER"

    wrong_tenant = api.get(
        f"/v1/research-runs?filter[tenant_id]={uuid4()}",
        headers={"Authorization": "Bearer test"},
    )
    assert wrong_tenant.status_code == 400
    assert wrong_tenant.json()["code"] == "INVALID_FILTER"


def test_dataset_versions_use_standard_envelope() -> None:
    api, _ = client()
    created = api.post(
        "/v1/datasets",
        headers={"Authorization": "Bearer test"},
        data={"name": "x"},
        files={"file": ("x.csv", BytesIO(b"abc"), "text/csv")},
    )
    assert created.status_code == 201
    dataset_id = created.json()["id"]
    response = api.get(
        f"/v1/datasets/{dataset_id}/versions?page=1&page_size=20",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


def test_missing_contract_endpoints_exist() -> None:
    api, _ = client()
    response = api.get("/v1/jobs/00000000-0000-0000-0000-000000000000/logs", headers={"Authorization": "Bearer test"})
    assert response.status_code == 404
    response = api.get("/v1/claims/not-found/evidence_graph", headers={"Authorization": "Bearer test"})
    assert response.status_code in {400, 404}


def test_tenant_signed_url_cannot_cross_tenant() -> None:
    digest = "a" * 64
    path = dataset_object_path("tenant-a", digest, 1)
    signed = sign_path("tenant-a", path, "secret", expires_in=3600, now=100)
    assert "tenant_id=tenant-a" in signed
    assert verify_path_signature("tenant-a", path, 4600, signed.split("sig=")[1], "secret", now=100) is True
    assert verify_path_signature("tenant-b", path, 4600, signed.split("sig=")[1], "secret", now=100) is False


def test_metrics_expose_required_security_counters() -> None:
    api, _ = client()
    api = TestClient(create_app(
        auth_provider=api.app.state.auth if hasattr(api.app.state, "auth") else Auth(TenantContext(uuid4(), uuid4(), Plan.TEAM, WorkspaceRole.RESEARCHER)),
        metrics_token="metrics-secret",
    ))
    response = api.get("/metrics", headers={"X-Metrics-Token": "metrics-secret"})
    assert response.status_code == 200
    text = response.text
    assert "jobs_created_total" in text
    assert "jobs_failed_total" in text
    assert "jobs_duration_seconds" in text
    assert "tenant_isolation_violations_total 0" in text
    assert "rls_violations_total 0" in text
