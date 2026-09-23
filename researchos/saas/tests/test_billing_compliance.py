from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from researchos.saas.api import create_app
from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole
from researchos.saas.entitlements import Entitlement, InMemoryEntitlementStore
from researchos.saas.persistence import InMemoryTenantPersistence, RetentionConfig
from researchos.saas.rate_limit import PlanRateLimiter
from researchos.saas.store import InMemoryResearchJobStore
from researchos.saas.contracts import ResearchJob, ResearchJobStatus


class StaticAuth:
    def __init__(self, context: TenantContext) -> None:
        self.context = context

    def authenticate(self, authorization: str | None, requested_workspace_id=None) -> TenantContext:
        del authorization
        if requested_workspace_id is not None and requested_workspace_id != self.context.workspace_id:
            raise ValueError("workspace mismatch")
        return self.context


def _client(*, context: TenantContext, store=None, entitlements=None, limiter=None, persistence=None) -> TestClient:
    return TestClient(
        create_app(
            auth_provider=StaticAuth(context),
            job_store=store or InMemoryResearchJobStore(),
            entitlement_store=entitlements or InMemoryEntitlementStore(),
            plan_rate_limiter=limiter or PlanRateLimiter(),
            tenant_persistence=persistence or InMemoryTenantPersistence(),
        )
    )


def _job(workspace_id, dataset_version_id):
    return ResearchJob(
        id=uuid4(),
        workspace_id=workspace_id,
        dataset_version_id=dataset_version_id,
        workflow_id="xauusd_m1_research_v1",
        status=ResearchJobStatus.SUCCEEDED,
        source_dataset_sha256="a" * 64,
    )


def test_free_tenant_101st_job_is_entitlement_exceeded() -> None:
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    dataset_version_id = uuid4()
    for _ in range(100):
        store.create(workspace_id, _job(workspace_id, dataset_version_id))
    entitlements = InMemoryEntitlementStore()
    entitlements.set(Entitlement(workspace_id, "free", 3, 100, 1024, 5))
    context = TenantContext(uuid4(), workspace_id, Plan.FREE, WorkspaceRole.OWNER)
    client = _client(context=context, store=store, entitlements=entitlements)

    response = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": str(uuid4())},
        json={"dataset_version_id": str(dataset_version_id), "workflow_id": "xauusd_m1_research_v1"},
    )
    assert response.status_code == 402
    body = response.json()
    assert body["code"] == "ENTITLEMENT_EXCEEDED"
    assert body["details"]["upgrade_url"] == "/billing/upgrade"
    assert response.headers["X-Request-ID"] == body["request_id"]


def test_workspace_rate_limit_returns_retry_after() -> None:
    workspace_id = uuid4()
    limiter = PlanRateLimiter(window_seconds=60)
    limiter.LIMITS[Plan.FREE] = 2
    context = TenantContext(uuid4(), workspace_id, Plan.FREE, WorkspaceRole.OWNER)
    client = _client(context=context, limiter=limiter)

    for _ in range(2):
        assert client.get("/v1/research-claims", headers={"Authorization": "Bearer test"}).status_code == 200
    response = client.get("/v1/research-claims", headers={"Authorization": "Bearer test"})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1
    assert response.json()["code"] == "RATE_LIMITED"


def test_soft_delete_hides_rows_and_retains_evidence_hash() -> None:
    workspace_id = uuid4()
    persistence = InMemoryTenantPersistence()
    persistence.add("dataset", "dataset-1", workspace_id, {"name": "D"})
    persistence.add("evidence", "evidence-1", workspace_id, {"content": "secret", "content_sha256": "b" * 64})
    deleted_at = datetime.now(timezone.utc)
    receipt = persistence.soft_delete_workspace(
        workspace_id,
        retention=RetentionConfig(30),
        deleted_at=deleted_at,
    )
    assert persistence.visible("dataset", workspace_id) == []
    assert persistence.visible("evidence", workspace_id) == []
    exported = persistence.export_workspace(workspace_id)
    assert b"historical_hash" in exported
    assert receipt.scheduled_purge_at == deleted_at + timedelta(days=30)


def test_workspace_delete_returns_receipt() -> None:
    workspace_id = uuid4()
    persistence = InMemoryTenantPersistence()
    persistence.add("dataset", "dataset-1", workspace_id, {"name": "D"})
    context = TenantContext(uuid4(), workspace_id, Plan.PRO, WorkspaceRole.OWNER)
    client = _client(context=context, persistence=persistence)

    response = client.delete(f"/v1/workspaces/{workspace_id}", headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    body = response.json()
    assert body["deletion_receipt_id"]
    assert body["scheduled_purge_at"]


def test_hard_purge_removes_expired_rows() -> None:
    workspace_id = uuid4()
    persistence = InMemoryTenantPersistence()
    persistence.add("dataset", "dataset-1", workspace_id, {"name": "D"})
    deleted_at = datetime.now(timezone.utc) - timedelta(days=31)
    persistence.soft_delete_workspace(workspace_id, retention=RetentionConfig(30), deleted_at=deleted_at)
    assert persistence.hard_purge_expired(now=datetime.now(timezone.utc)) == 1
    assert persistence.export_workspace(workspace_id).find(b"dataset-1") == -1
