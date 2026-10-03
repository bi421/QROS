from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from researchos.claims.claim import ResearchClaim
from researchos.saas.api import create_app
from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole
from researchos.saas.finding_api import InMemoryResearchFindingStore


class StaticAuth:
    def __init__(self, context: TenantContext) -> None:
        self.context = context

    def authenticate(
        self,
        authorization: str | None,
        requested_workspace_id: UUID | None = None,
    ) -> TenantContext:
        del authorization
        if requested_workspace_id is not None and requested_workspace_id != self.context.workspace_id:
            raise ValueError("workspace mismatch")
        return self.context


class EmptyClaimStore:
    def save(self, workspace_id: UUID, claim: ResearchClaim) -> ResearchClaim:
        return claim

    def get(self, workspace_id: UUID, claim_id: str) -> ResearchClaim | None:
        return None

    def list(
        self,
        workspace_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        status: str | None = None,
    ) -> tuple[list[ResearchClaim], int]:
        return [], 0


@pytest.fixture()
def client() -> TestClient:
    context = TenantContext(
        user_id=uuid4(),
        workspace_id=uuid4(),
        plan=Plan.PRO,
        role=WorkspaceRole.OWNER,
    )
    return TestClient(
        create_app(
            auth_provider=StaticAuth(context),
            claim_store=EmptyClaimStore(),
            finding_store=InMemoryResearchFindingStore(),
        )
    )


@pytest.mark.parametrize(
    "path",
    [
        "/v1/datasets",
        "/v1/research-runs",
        "/v1/research-claims",
        "/v1/findings",
    ],
)
def test_all_list_endpoints_return_standard_pagination_envelope(
    client: TestClient,
    path: str,
) -> None:
    response = client.get(path, headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "pagination", "request_id"}
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["pagination"] == {
        "page": 1,
        "page_size": 20,
        "total": 0,
        "total_pages": 0,
    }
    assert body["data"] == []


@pytest.mark.parametrize(
    "path",
    [
        "/v1/datasets",
        "/v1/research-runs",
        "/v1/research-claims",
        "/v1/findings",
        "/v1/datasets/00000000-0000-0000-0000-000000000000/versions",
        "/v1/research-runs/00000000-0000-0000-0000-000000000000/logs",
        "/v1/jobs/00000000-0000-0000-0000-000000000000/logs",
        "/v1/claims/00000000-0000-0000-0000-000000000000/evidence_graph",
    ],
)
def test_page_size_overflow_is_client_error(
    client: TestClient,
    path: str,
) -> None:
    response = client.get(
        f"{path}?page_size=101",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "path",
    [
        "/v1/datasets",
        "/v1/research-runs",
        "/v1/research-claims",
        "/v1/findings",
    ],
)
def test_invalid_sort_field_returns_invalid_sort_code(
    client: TestClient,
    path: str,
) -> None:
    response = client.get(
        f"{path}?sort_by=not_a_real_field",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_SORT"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["correlation_id"] == body["request_id"]


def test_invalid_filter_returns_structured_400(client: TestClient) -> None:
    response = client.get(
        "/v1/findings?filter%5Bunknown%5D=x",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_FILTER"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["correlation_id"] == body["request_id"]


def test_openapi_contains_contract_alias_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/datasets/{dataset_id}/versions" in paths
    assert "/v1/jobs/{job_id}/logs" in paths
    assert "/v1/claims/{claim_id}/evidence_graph" in paths


def test_standard_filter_syntax_is_accepted_for_jobs(client: TestClient) -> None:
    response = client.get(
        "/v1/research-runs?page=1&page_size=20&sort_by=created_at&sort_order=desc&filter%5Bstatus%5D=completed",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 200
    assert response.json()["pagination"]["page_size"] == 20
