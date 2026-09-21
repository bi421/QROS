from io import BytesIO
from uuid import UUID, uuid4
import hashlib
import hmac
import json
import threading

from fastapi import HTTPException
from fastapi.testclient import TestClient

from researchos.research_core.contracts import FROZEN_XAUUSD_M1_WORKFLOW
from researchos.saas.api import create_app
from researchos.claims.claim import ResearchClaim
from researchos.saas.billing import InMemoryBillingEventStore
from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole
from researchos.saas.datasets import InMemoryDatasetStorage, InMemoryDatasetStore
from researchos.saas.store import InMemoryResearchJobStore


class StaticAuth:
    def __init__(self, context: TenantContext) -> None:
        self.context = context

    def authenticate(self, authorization: str | None, requested_workspace_id: UUID | None = None) -> TenantContext:
        assert authorization == "Bearer test"
        if requested_workspace_id is not None and requested_workspace_id != self.context.workspace_id:
            raise HTTPException(status_code=403, detail="workspace access denied")
        return self.context


class StaticRateLimiter:
    def __init__(self, allowed: bool = True, error: Exception | None = None) -> None:
        self.allowed = allowed
        self.error = error
        self.keys: list[str] = []

    def allow(self, key: str) -> bool:
        self.keys.append(key)
        if self.error is not None:
            raise self.error
        return self.allowed


def _client(workspace_id: UUID | None = None, *, plan: Plan = Plan.PRO, role: WorkspaceRole = WorkspaceRole.RESEARCHER, billing_store=None, billing_secret=None, rate_limiter=None, claim_store=None):
    context = TenantContext(
        user_id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        plan=plan,
        role=role,
    )
    dataset_store = InMemoryDatasetStore()
    dataset_storage = InMemoryDatasetStorage()
    client = TestClient(
        create_app(
            auth_provider=StaticAuth(context),
            job_store=InMemoryResearchJobStore(),
            dataset_store=dataset_store,
            dataset_storage=dataset_storage,
            billing_store=billing_store,
            billing_webhook_secret=billing_secret,
            rate_limiter=rate_limiter,
            claim_store=claim_store,
        )
    )
    return client, context, dataset_store, dataset_storage



class InMemoryClaimStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, str], ResearchClaim] = {}

    def save(self, workspace_id: UUID, claim: ResearchClaim) -> ResearchClaim:
        if claim.workspace_id != str(workspace_id):
            raise ValueError("research claim workspace does not match tenant")
        self.rows[(workspace_id, claim.id)] = claim
        return claim

    def get(self, workspace_id: UUID, claim_id: str) -> ResearchClaim | None:
        return self.rows.get((workspace_id, claim_id))

    def list(self, workspace_id: UUID, *, limit: int = 100, offset: int = 0):
        values = [claim for (ws, _), claim in self.rows.items() if ws == workspace_id]
        values.sort(key=lambda claim: claim.id)
        return values[offset:offset + limit], len(values)

def _upload(client: TestClient, name: str, body: bytes):
    return client.post(
        "/v1/datasets",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "test-key"},
        data={"name": name},
        files={"file": (f"{name}.csv", BytesIO(body), "text/csv")},
    )


def test_health_does_not_require_authentication() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(response.headers["X-Request-ID"]) == 36


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


def test_rate_limit_is_workspace_scoped_and_enforced() -> None:
    limiter = StaticRateLimiter(allowed=False)
    client, context, _, _ = _client(rate_limiter=limiter)
    response = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "rate-limit"},
        json={"dataset_version_id": str(uuid4())},
    )
    assert response.status_code == 429
    assert limiter.keys == [hashlib.sha256(f"workspace:{context.workspace_id}".encode()).hexdigest()]


def test_rate_limiter_failure_fails_closed_with_503() -> None:
    client, _, _, _ = _client(rate_limiter=StaticRateLimiter(error=RuntimeError("db down")))
    response = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "rate-limit-failure"},
        json={"dataset_version_id": str(uuid4())},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "rate limiting service unavailable"


def test_health_bypasses_rate_limiter() -> None:
    limiter = StaticRateLimiter(allowed=False)
    client, _, _, _ = _client(rate_limiter=limiter)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert limiter.keys == []


def test_dataset_upload_creates_immutable_version_and_stores_bytes() -> None:
    client, context, store, storage = _client()
    body = b"timestamp,open,high,low,close\n1,10,11,9,10\n"
    response = _upload(client, "sample-xauusd", body)
    assert response.status_code == 201
    payload = response.json()
    assert payload["workspace_id"] == str(context.workspace_id)
    assert payload["version"]["version_no"] == 1
    assert payload["version"]["byte_size"] == len(body)
    assert len(payload["version"]["content_sha256"]) == 64

    versions = client.get(
        f"/v1/datasets/{payload['id']}/versions",
        headers={"Authorization": "Bearer test"},
    )
    assert versions.status_code == 200
    assert len(versions.json()) == 1
    version = versions.json()[0]
    assert version["id"] == payload["version"]["id"]
    assert storage.get(version["storage_path"]) == body
    assert store.get_dataset(context.workspace_id, UUID(payload["id"])) is not None


def test_dataset_versions_are_append_only() -> None:
    client, _, _, _ = _client()
    first = _upload(client, "sample", b"a")
    assert first.status_code == 201
    dataset_id = first.json()["id"]

    second = client.post(
        f"/v1/datasets/{dataset_id}/versions",
        headers={"Authorization": "Bearer test"},
        files={"file": ("sample-v2.csv", BytesIO(b"b"), "text/csv")},
    )
    assert second.status_code == 201
    assert second.json()["version_no"] == 2

    versions = client.get(
        f"/v1/datasets/{dataset_id}/versions",
        headers={"Authorization": "Bearer test"},
    )
    assert versions.status_code == 200
    assert [item["version_no"] for item in versions.json()] == [1, 2]


def test_create_research_job_requires_existing_tenant_dataset_version() -> None:
    client, _, _, _ = _client()
    response = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "missing-version"},
        json={"dataset_version_id": str(uuid4())},
    )
    assert response.status_code == 404


def test_research_run_idempotency_replays_without_creating_or_enqueueing_twice() -> None:
    client, _, _, _ = _client()
    uploaded = _upload(client, "sample-idempotent", b"x")
    version_id = uploaded.json()["version"]["id"]
    headers = {"Authorization": "Bearer test", "Idempotency-Key": "same-run"}
    first = client.post(
        "/v1/research-runs",
        headers=headers,
        json={"dataset_version_id": version_id},
    )
    second = client.post(
        "/v1/research-runs",
        headers=headers,
        json={"dataset_version_id": version_id},
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]

def test_research_run_idempotency_is_atomic_under_concurrent_requests() -> None:
    client, _, _, _ = _client()
    uploaded = _upload(client, "sample-concurrent-idempotency", b"x")
    version_id = uploaded.json()["version"]["id"]
    headers = {"Authorization": "Bearer test", "Idempotency-Key": "concurrent-run"}
    barrier = threading.Barrier(2)
    responses = []

    def submit() -> None:
        barrier.wait()
        responses.append(
            client.post(
                "/v1/research-runs",
                headers=headers,
                json={"dataset_version_id": version_id},
            )
        )

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert [response.status_code for response in responses] == [202, 202]
    assert {response.json()["id"] for response in responses}.__len__() == 1


def test_research_run_list_supports_tenant_scoped_pagination_and_filters() -> None:
    # The API enforces the tenant plan concurrency limit. This test needs
    # three simultaneously queued runs to exercise pagination, so use TEAM
    # explicitly rather than weakening the production limit or rate limiter.
    client, context, _, _ = _client(plan=Plan.TEAM)
    uploaded = _upload(client, "sample-list", b"x")
    version_id = uploaded.json()["version"]["id"]
    for key in ("list-a", "list-b", "list-c"):
        response = client.post(
            "/v1/research-runs",
            headers={"Authorization": "Bearer test", "Idempotency-Key": key},
            json={"dataset_version_id": version_id},
        )
        assert response.status_code == 202

    page = client.get(
        "/v1/research-runs?limit=2&offset=1&status_filter=queued",
        headers={"Authorization": "Bearer test"},
    )
    assert page.status_code == 200
    payload = page.json()
    assert payload["total"] == 3
    assert payload["limit"] == 2
    assert payload["offset"] == 1
    assert len(payload["items"]) == 2
    assert payload["has_more"] is False
    assert all(item["workspace_id"] == str(context.workspace_id) for item in payload["items"])

    empty = client.get(
        "/v1/research-runs?limit=100&offset=0&workflow_id=not-this-workflow",
        headers={"Authorization": "Bearer test"},
    )
    assert empty.status_code == 200
    assert empty.json()["total"] == 0
    assert empty.json()["items"] == []


def test_research_run_list_rejects_unbounded_pagination() -> None:
    client, _, _, _ = _client()
    response = client.get(
        "/v1/research-runs?limit=101",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 422


def test_create_and_get_research_job_are_tenant_scoped() -> None:
    client, context, _, _ = _client()
    uploaded = _upload(client, "sample", b"x")
    version_id = uploaded.json()["version"]["id"]
    response = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "create-run"},
        json={"dataset_version_id": version_id},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["workspace_id"] == str(context.workspace_id)
    assert payload["status"] == "queued"
    assert payload["workflow_id"] == FROZEN_XAUUSD_M1_WORKFLOW
    assert payload["dataset_version_id"] == version_id

    job_id = payload["id"]
    fetched = client.get(
        f"/v1/research-runs/{job_id}",
        headers={"Authorization": "Bearer test"},
    )
    assert fetched.status_code == 200
    assert fetched.json()["id"] == job_id


def test_unsupported_workflow_is_rejected() -> None:
    client, _, _, _ = _client()
    response = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test"},
        json={"dataset_version_id": str(uuid4()), "workflow_id": "arbitrary"},
    )
    assert response.status_code == 400


def test_cross_tenant_job_lookup_returns_404() -> None:
    store = InMemoryResearchJobStore()
    owner = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    other = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    owner_datasets = InMemoryDatasetStore()
    owner_storage = InMemoryDatasetStorage()
    owner_client = TestClient(
        create_app(
            auth_provider=StaticAuth(owner),
            job_store=store,
            dataset_store=owner_datasets,
            dataset_storage=owner_storage,
        )
    )
    other_client = TestClient(
        create_app(
            auth_provider=StaticAuth(other),
            job_store=store,
            dataset_store=owner_datasets,
            dataset_storage=owner_storage,
        )
    )
    created_dataset = _upload(owner_client, "sample", b"x")
    created = owner_client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "cross-tenant-create"},
        json={"dataset_version_id": created_dataset.json()["version"]["id"]},
    )
    job_id = created.json()["id"]

    response = other_client.get(
        f"/v1/research-runs/{job_id}",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 404


def test_cross_tenant_dataset_and_version_access_returns_not_found() -> None:
    owner = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    other = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    store = InMemoryDatasetStore()
    storage = InMemoryDatasetStorage()
    owner_client = TestClient(create_app(
        auth_provider=StaticAuth(owner),
        dataset_store=store,
        dataset_storage=storage,
        job_store=InMemoryResearchJobStore(),
    ))
    other_client = TestClient(create_app(
        auth_provider=StaticAuth(other),
        dataset_store=store,
        dataset_storage=storage,
        job_store=InMemoryResearchJobStore(),
    ))

    created = _upload(owner_client, "tenant-owned", b"x")
    assert created.status_code == 201
    dataset_id = created.json()["id"]
    version_id = created.json()["version"]["id"]

    assert other_client.get(
        f"/v1/datasets/{dataset_id}/versions",
        headers={"Authorization": "Bearer test"},
    ).json() == []
    assert other_client.post(
        f"/v1/datasets/{dataset_id}/versions",
        headers={"Authorization": "Bearer test"},
        files={"file": ("cross-tenant.csv", BytesIO(b"y"), "text/csv")},
    ).status_code == 404

    run = other_client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "cross-tenant-dataset"},
        json={"dataset_version_id": version_id},
    )
    assert run.status_code == 404
    assert other_client.get(
        f"/v1/datasets/{dataset_id}/versions/{version_id}/download",
        headers={"Authorization": "Bearer test"},
    ).status_code == 404


def test_dataset_download_url_is_authorized_and_short_lived() -> None:
    client, _, _, _ = _client()
    created = _upload(client, "downloadable", b"dataset")
    dataset_id = created.json()["id"]
    version_id = created.json()["version"]["id"]

    response = client.get(
        f"/v1/datasets/{dataset_id}/versions/{version_id}/download",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    assert response.json()["expires_in"] == "300"
    assert response.json()["url"].startswith("memory://")


def test_dataset_download_rejects_dataset_version_mismatch() -> None:
    client, _, _, _ = _client()
    first = _upload(client, "first", b"one")
    second = _upload(client, "second", b"two")

    response = client.get(
        f"/v1/datasets/{first.json()['id']}/versions/{second.json()['version']['id']}/download",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 404


def test_billing_webhook_processes_and_replays_identical_event() -> None:
    billing = InMemoryBillingEventStore()
    client, _, _, _ = _client(billing_store=billing, billing_secret="secret")
    payload = json.dumps({
        "event_id": "evt_1",
        "workspace_id": str(uuid4()),
        "plan": "pro",
        "status": "active",
    }).encode()
    signature = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()
    headers = {
        "X-Billing-Signature": signature,
        "X-Billing-Provider": "test",
    }

    first = client.post("/v1/billing/webhook", content=payload, headers=headers)
    replay = client.post("/v1/billing/webhook", content=payload, headers=headers)

    assert first.status_code == 200
    assert first.json() == {"status": "processed"}
    assert replay.status_code == 200
    assert replay.json() == {"status": "replayed"}


def test_billing_webhook_rejects_invalid_signature() -> None:
    billing = InMemoryBillingEventStore()
    client, _, _, _ = _client(billing_store=billing, billing_secret="secret")
    response = client.post(
        "/v1/billing/webhook",
        content=b'{"event_id":"evt_1","workspace_id":"w","plan":"pro","status":"active"}',
        headers={"X-Billing-Signature": "bad", "X-Billing-Provider": "test"},
    )
    assert response.status_code == 401



def test_http_errors_include_structured_error_metadata() -> None:
    client = TestClient(create_app())
    response = client.get("/v1/me", headers={"Authorization": "Bearer anything", "X-Request-ID": "req-structured"})
    assert response.status_code == 503
    payload = response.json()
    assert payload["detail"] == "SaaS authentication provider is not configured"
    assert payload["error"] == {
        "code": "service_unavailable",
        "message": "SaaS authentication provider is not configured",
        "request_id": "req-structured",
    }


def test_validation_errors_include_structured_error_metadata() -> None:
    client, _, _, _ = _client()
    response = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "validation"},
        json={"dataset_version_id": "not-a-uuid"},
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["request_id"]
    assert isinstance(payload["detail"], list)


def test_invalid_workspace_header_is_rejected() -> None:
    client, _, _, _ = _client()
    response = client.get("/v1/me", headers={"Authorization": "Bearer test", "X-Workspace-ID": "not-a-uuid"})
    assert response.status_code == 422


def test_viewer_can_read_but_cannot_mutate_datasets_or_research() -> None:
    client, _, _, _ = _client(role=WorkspaceRole.VIEWER)
    health = client.get("/v1/me", headers={"Authorization": "Bearer test"})
    assert health.status_code == 200
    upload = _upload(client, "viewer-upload", b"x")
    assert upload.status_code == 403
    run = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "viewer-run"},
        json={"dataset_version_id": str(uuid4())},
    )
    assert run.status_code == 403


def test_researcher_can_create_dataset_and_research_run() -> None:
    client, _, _, _ = _client(role=WorkspaceRole.RESEARCHER)
    uploaded = _upload(client, "researcher-upload", b"x")
    assert uploaded.status_code == 201
    version_id = uploaded.json()["version"]["id"]
    run = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "researcher-run"},
        json={"dataset_version_id": version_id},
    )
    assert run.status_code == 202


def test_admin_can_create_dataset_and_research_run() -> None:
    client, _, _, _ = _client(role=WorkspaceRole.ADMIN)
    uploaded = _upload(client, "admin-upload", b"x")
    assert uploaded.status_code == 201
    run = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "admin-run"},
        json={"dataset_version_id": uploaded.json()["version"]["id"]},
    )
    assert run.status_code == 202


def test_cross_tenant_research_run_list_and_idempotency_key_are_isolated() -> None:
    store = InMemoryResearchJobStore()
    owner = TenantContext(uuid4(), uuid4(), Plan.TEAM, WorkspaceRole.RESEARCHER)
    other = TenantContext(uuid4(), uuid4(), Plan.TEAM, WorkspaceRole.RESEARCHER)
    dataset_store = InMemoryDatasetStore()
    dataset_storage = InMemoryDatasetStorage()

    owner_client = TestClient(create_app(
        auth_provider=StaticAuth(owner),
        job_store=store,
        dataset_store=dataset_store,
        dataset_storage=dataset_storage,
    ))
    other_client = TestClient(create_app(
        auth_provider=StaticAuth(other),
        job_store=store,
        dataset_store=dataset_store,
        dataset_storage=dataset_storage,
    ))

    owner_dataset = _upload(owner_client, "owner-dataset", b"owner")
    other_dataset = _upload(other_client, "other-dataset", b"other")
    assert owner_dataset.status_code == 201
    assert other_dataset.status_code == 201

    # The same idempotency key is safe to reuse across tenants because the
    # durable key is scoped by workspace, not globally.
    shared_key = "shared-red-team-key"
    owner_run = owner_client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": shared_key},
        json={"dataset_version_id": owner_dataset.json()["version"]["id"]},
    )
    other_run = other_client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": shared_key},
        json={"dataset_version_id": other_dataset.json()["version"]["id"]},
    )

    assert owner_run.status_code == 202
    assert other_run.status_code == 202
    assert owner_run.json()["id"] != other_run.json()["id"]
    assert owner_run.json()["workspace_id"] == str(owner.workspace_id)
    assert other_run.json()["workspace_id"] == str(other.workspace_id)

    owner_list = owner_client.get(
        "/v1/research-runs?limit=100&offset=0",
        headers={"Authorization": "Bearer test"},
    )
    other_list = other_client.get(
        "/v1/research-runs?limit=100&offset=0",
        headers={"Authorization": "Bearer test"},
    )

    assert owner_list.status_code == 200
    assert other_list.status_code == 200
    assert owner_list.json()["total"] == 1
    assert other_list.json()["total"] == 1
    assert {item["id"] for item in owner_list.json()["items"]} == {owner_run.json()["id"]}
    assert {item["id"] for item in other_list.json()["items"]} == {other_run.json()["id"]}


def test_cross_tenant_workspace_header_cannot_select_another_workspace() -> None:
    owner = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    other = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    client = TestClient(create_app(auth_provider=StaticAuth(owner)))

    response = client.get(
        "/v1/me",
        headers={
            "Authorization": "Bearer test",
            "X-Workspace-ID": str(other.workspace_id),
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "workspace access denied"


def test_governed_research_run_requires_locked_claim_plan_and_persists_binding() -> None:
    claim_store = InMemoryClaimStore()
    client, _, _, _ = _client(claim_store=claim_store)
    created = client.post(
        "/v1/research-claims",
        headers={"Authorization": "Bearer test"},
        json={"statement": "DXY shocks are associated with XAUUSD returns."},
    )
    assert created.status_code == 201
    claim_id = created.json()["id"]

    uploaded = _upload(client, "governed-run", b"x")
    version_id = uploaded.json()["version"]["id"]
    missing_lock = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "governed-missing-lock"},
        json={"dataset_version_id": version_id, "claim_id": claim_id, "plan_hash": "a" * 64},
    )
    assert missing_lock.status_code == 409

    plan = {
        "hypothesis": "DXY shocks are associated with XAUUSD returns.",
        "sample_definition": "XAUUSD M1 2021-2025",
        "features": ["return_1"], "labels": ["return_60m"],
        "train_validation_test": "time ordered 60/20/20",
        "exclusions": [], "costs_slippage": "explicit",
        "statistical_tests": ["paired bootstrap"], "metrics": ["mean_return"],
        "stopping_rules": ["no early stopping"],
        "multiple_testing_policy": "pre-registered",
        "replication_policy": "independent holdout",
    }
    locked = client.post(
        f"/v1/research-claims/{claim_id}/plan-lock",
        headers={"Authorization": "Bearer test"}, json=plan,
    )
    assert locked.status_code == 200
    plan_hash = locked.json()["plan_hash"]

    run = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "governed-run"},
        json={"dataset_version_id": version_id, "claim_id": claim_id, "plan_hash": plan_hash},
    )
    assert run.status_code == 202
    body = run.json()
    assert body["claim_id"] == claim_id
    assert body["plan_hash"] == plan_hash
