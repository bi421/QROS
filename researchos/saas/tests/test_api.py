from __future__ import annotations

from io import BytesIO
from uuid import UUID, uuid4
import hashlib
import hmac
import json
import threading

from fastapi.testclient import TestClient

from researchos.research_core.contracts import FROZEN_XAUUSD_M1_WORKFLOW
from researchos.saas.api import create_app
from researchos.saas.billing import (
    Entitlement,
    InMemoryBillingEventStore,
    InMemoryBillingProvider,
    InMemoryEntitlementStore,
)
from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole
from researchos.saas.datasets import InMemoryDatasetStorage, InMemoryDatasetStore
from researchos.saas.store import InMemoryResearchJobStore


class StaticAuth:
    def __init__(self, context: TenantContext) -> None:
        self.context = context

    def authenticate_user(self, authorization: str | None) -> UUID:
        assert authorization == "Bearer test"
        return self.context.user_id

    def authenticate(self, authorization: str | None) -> TenantContext:
        assert authorization == "Bearer test"
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


def _client(workspace_id: UUID | None = None, *, billing_store=None, billing_secret=None, rate_limiter=None):
    context = TenantContext(
        user_id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        plan=Plan.PRO,
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
        )
    )
    return client, context, dataset_store, dataset_storage


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
    assert response.json()["code"] == "service_unavailable"
    assert response.json()["message"] == "rate limiting service unavailable"


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
    payload_versions = versions.json()
    assert payload_versions["pagination"]["total"] == 1
    version = payload_versions["data"][0]
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
    assert [item["version_no"] for item in versions.json()["data"]] == [2, 1]


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


def test_idempotency_key_is_partitioned_by_workspace_and_never_replays_foreign_response() -> None:
    """Two workspaces sharing one job store must not collide on an identical key.

    The idempotency map is keyed by (workspace_id, key); workspace B reusing
    workspace A's key must receive a fresh B-scoped run, never A's response, and
    must not be able to resolve A's dataset version.
    """
    shared_jobs = InMemoryResearchJobStore()
    shared_datasets = InMemoryDatasetStore()

    ctx_a = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.OWNER)
    ctx_b = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.OWNER)

    def app_for(ctx: TenantContext) -> TestClient:
        return TestClient(create_app(
            auth_provider=StaticAuth(ctx),
            job_store=shared_jobs,
            dataset_store=shared_datasets,
            dataset_storage=InMemoryDatasetStorage(),
        ))

    client_a = app_for(ctx_a)
    client_b = app_for(ctx_b)

    version_a = _upload(client_a, "ws-a-dataset", b"x").json()["version"]["id"]
    version_b = _upload(client_b, "ws-b-dataset", b"x").json()["version"]["id"]

    key = "SAME_KEY"
    resp_a = client_a.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": key},
        json={"dataset_version_id": version_a},
    )
    assert resp_a.status_code == 202
    body_a = resp_a.json()
    assert body_a["workspace_id"] == str(ctx_a.workspace_id)

    resp_b = client_b.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": key},
        json={"dataset_version_id": version_b},
    )
    assert resp_b.status_code == 202
    body_b = resp_b.json()

    assert body_b["workspace_id"] == str(ctx_b.workspace_id)
    assert body_b["id"] != body_a["id"]
    assert body_b["dataset_version_id"] == version_b
    assert body_a["id"] not in resp_b.text
    assert str(ctx_a.workspace_id) not in resp_b.text
    assert version_a not in resp_b.text

    cross = client_b.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "other-key"},
        json={"dataset_version_id": version_a},
    )
    assert cross.status_code == 404

    job_a = shared_jobs.get(ctx_a.workspace_id, UUID(body_a["id"]))
    job_b = shared_jobs.get(ctx_b.workspace_id, UUID(body_b["id"]))
    assert job_a is not None and job_a.workspace_id == ctx_a.workspace_id
    assert job_b is not None and job_b.workspace_id == ctx_b.workspace_id
    assert shared_jobs.get(ctx_b.workspace_id, UUID(body_a["id"])) is None
    assert shared_jobs.get(ctx_a.workspace_id, UUID(body_b["id"])) is None


def test_idempotency_key_reuse_with_different_fingerprint_fails_closed_without_overwrite() -> None:
    """Same workspace + same key + different request fingerprint must 409.

    The failed attempt must not overwrite the stored fingerprint/response, must
    not mutate the original run, and must not create a second resource: replaying
    the ORIGINAL fingerprint still returns the original run.
    """
    client, context, _, _ = _client()
    version_1 = _upload(client, "fp-one", b"x").json()["version"]["id"]
    version_2 = _upload(client, "fp-two", b"y").json()["version"]["id"]
    key = "conflict-key"

    first = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": key},
        json={"dataset_version_id": version_1},
    )
    assert first.status_code == 202
    job_id = first.json()["id"]

    conflicting = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": key},
        json={"dataset_version_id": version_2},
    )
    assert conflicting.status_code == 409
    assert "reused" in conflicting.text

    replay = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": key},
        json={"dataset_version_id": version_1},
    )
    assert replay.status_code == 202
    assert replay.json()["id"] == job_id
    assert replay.json()["dataset_version_id"] == version_1

    fetched = client.get(
        f"/v1/research-runs/{job_id}", headers={"Authorization": "Bearer test"}
    )
    assert fetched.status_code == 200
    assert fetched.json()["workspace_id"] == str(context.workspace_id)
    assert fetched.json()["dataset_version_id"] == version_1


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
    owner = TenantContext(uuid4(), uuid4(), Plan.PRO)
    other = TenantContext(uuid4(), uuid4(), Plan.PRO)
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
    owner = TenantContext(uuid4(), uuid4(), Plan.PRO)
    other = TenantContext(uuid4(), uuid4(), Plan.PRO)
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
    ).json()["data"] == []
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
    assert response.json()["expires_in"] == "3600"
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
        "X-Billing-Provider": "hmac",
    }

    first = client.post("/v1/billing/webhook", content=payload, headers=headers)
    replay = client.post("/v1/billing/webhook", content=payload, headers=headers)

    assert first.status_code == 200
    assert first.json() == {"status": "processed"}
    assert replay.status_code == 200
    assert replay.json() == {"status": "replayed"}



def test_billing_webhook_binds_signature_scheme_to_declared_provider() -> None:
    billing = InMemoryBillingEventStore()
    client, _, _, _ = _client(billing_store=billing, billing_secret="secret")
    payload = json.dumps({
        "event_id": "evt_provider_mismatch",
        "workspace_id": str(uuid4()),
        "plan": "pro",
        "status": "active",
    }).encode()
    signature = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()
    response = client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "X-Billing-Signature": signature,
            "X-Billing-Provider": "stripe",
        },
    )
    assert response.status_code == 401


def test_billing_webhook_rejects_invalid_signature() -> None:
    billing = InMemoryBillingEventStore()
    client, _, _, _ = _client(billing_store=billing, billing_secret="secret")
    response = client.post(
        "/v1/billing/webhook",
        content=b'{"event_id":"evt_1","workspace_id":"w","plan":"pro","status":"active"}',
        headers={"X-Billing-Signature": "bad", "X-Billing-Provider": "hmac"},
    )
    assert response.status_code == 401


class _UnavailableEntitlementStore:
    """Entitlement backend that fails on every access; must never degrade to allow."""

    def get(self, tenant_id: UUID, plan: str) -> Entitlement:
        raise RuntimeError("entitlement backend unavailable")

    def upsert(self, entitlement: Entitlement) -> Entitlement:
        raise RuntimeError("entitlement backend unavailable")


def test_entitlement_service_failure_fails_closed_and_creates_no_run() -> None:
    context = TenantContext(user_id=uuid4(), workspace_id=uuid4(), plan=Plan.PRO)
    jobs = InMemoryResearchJobStore()
    client = TestClient(
        create_app(
            auth_provider=StaticAuth(context),
            job_store=jobs,
            dataset_store=InMemoryDatasetStore(),
            dataset_storage=InMemoryDatasetStorage(),
            entitlement_store=_UnavailableEntitlementStore(),
        )
    )

    response = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "entitlement-down"},
        json={"dataset_version_id": str(uuid4())},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "service_unavailable"
    assert response.json()["message"] == "entitlement service unavailable"
    assert jobs.count_active(context.workspace_id) == 0
    assert jobs.count_monthly(context.workspace_id) == 0


def test_monthly_job_entitlement_exceeded_returns_402_without_creating_run() -> None:
    context = TenantContext(user_id=uuid4(), workspace_id=uuid4(), plan=Plan.PRO)
    jobs = InMemoryResearchJobStore()
    entitlements = InMemoryEntitlementStore()
    entitlements.upsert(
        Entitlement(
            tenant_id=context.workspace_id,
            plan="pro",
            max_datasets=1000,
            max_jobs_per_month=1,
            max_storage_mb=10240,
        )
    )
    client = TestClient(
        create_app(
            auth_provider=StaticAuth(context),
            job_store=jobs,
            dataset_store=InMemoryDatasetStore(),
            dataset_storage=InMemoryDatasetStorage(),
            entitlement_store=entitlements,
        )
    )
    version_id = _upload(client, "monthly-quota", b"x").json()["version"]["id"]

    first = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "quota-1"},
        json={"dataset_version_id": version_id},
    )
    second = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "quota-2"},
        json={"dataset_version_id": version_id},
    )

    assert first.status_code == 202
    assert second.status_code == 402
    assert second.json()["code"] == "ENTITLEMENT_EXCEEDED"
    assert jobs.count_monthly(context.workspace_id) == 1


def test_concurrency_limit_returns_429_without_creating_additional_run() -> None:
    context = TenantContext(user_id=uuid4(), workspace_id=uuid4(), plan=Plan.PRO)
    jobs = InMemoryResearchJobStore()
    client = TestClient(
        create_app(
            auth_provider=StaticAuth(context),
            job_store=jobs,
            dataset_store=InMemoryDatasetStore(),
            dataset_storage=InMemoryDatasetStorage(),
        )
    )
    version_id = _upload(client, "concurrency", b"x").json()["version"]["id"]

    def _create(key: str):
        return client.post(
            "/v1/research-runs",
            headers={"Authorization": "Bearer test", "Idempotency-Key": key},
            json={"dataset_version_id": version_id},
        )

    assert _create("concurrency-1").status_code == 202
    assert _create("concurrency-2").status_code == 202
    assert jobs.count_active(context.workspace_id) == 2

    third = _create("concurrency-3")

    assert third.status_code == 429
    assert third.json()["code"] == "rate_limited"
    assert third.json()["message"] == "concurrent research run limit reached"
    assert jobs.count_active(context.workspace_id) == 2


def test_billing_webhook_rejects_event_id_reuse_with_different_payload() -> None:
    billing = InMemoryBillingEventStore()
    client, _, _, _ = _client(billing_store=billing, billing_secret="secret")
    workspace_id = str(uuid4())
    original = json.dumps(
        {"event_id": "evt_reuse", "workspace_id": workspace_id, "plan": "pro", "status": "active"}
    ).encode()
    tampered = json.dumps(
        {"event_id": "evt_reuse", "workspace_id": workspace_id, "plan": "enterprise", "status": "active"}
    ).encode()

    def _post(body: bytes):
        signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
        return client.post(
            "/v1/billing/webhook",
            content=body,
            headers={"X-Billing-Signature": signature, "X-Billing-Provider": "hmac"},
        )

    first = _post(original)
    assert first.status_code == 200
    assert first.json() == {"status": "processed"}

    assert _post(tampered).status_code == 409

    replay = _post(original)
    assert replay.status_code == 200
    assert replay.json() == {"status": "replayed"}



def test_http_errors_include_structured_error_metadata() -> None:
    client = TestClient(create_app())
    response = client.get("/v1/me", headers={"Authorization": "Bearer anything", "X-Request-ID": "req-structured"})
    assert response.status_code == 503
    payload = response.json()
    assert payload == {
        "code": "service_unavailable",
        "message": "SaaS authentication provider is not configured",
        "request_id": "req-structured",
        "correlation_id": "req-structured",
    }


def test_validation_errors_include_structured_error_metadata() -> None:
    client, _, _, _ = _client()
    response = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "validation"},
        json={"dataset_version_id": "not-a-uuid"},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "validation_error"
    assert payload["message"] == "Request validation failed"
    assert payload["request_id"]
    assert payload["correlation_id"] == payload["request_id"]


def test_dataset_versions_reject_invalid_sort_and_filter() -> None:
    client, _, _, _ = _client()
    created = _upload(client, "sort-filter", b"x")
    dataset_id = created.json()["id"]
    bad_sort = client.get(f"/v1/datasets/{dataset_id}/versions?sort_by=not_a_field", headers={"Authorization": "Bearer test"})
    assert bad_sort.status_code == 400
    assert bad_sort.json()["code"] == "INVALID_SORT"
    assert bad_sort.json()["request_id"] == bad_sort.headers["X-Request-ID"]
    bad_filter = client.get(f"/v1/datasets/{dataset_id}/versions?filter[status]=completed", headers={"Authorization": "Bearer test"})
    assert bad_filter.status_code == 400
    assert bad_filter.json()["code"] == "INVALID_FILTER"

def test_readiness_probe_failure_fails_closed() -> None:
    def probe() -> None:
        raise RuntimeError("database unavailable")

    client = TestClient(create_app(readiness_probe=probe))
    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "code": "service_unavailable",
        "message": "SaaS dependency readiness check failed",
        "request_id": response.headers["X-Request-ID"],
        "correlation_id": response.headers["X-Request-ID"],
    }


def test_readiness_probe_success_keeps_endpoint_ready() -> None:
    calls = []

    def probe() -> None:
        calls.append("checked")

    client = TestClient(create_app(readiness_probe=probe))
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert calls == ["checked"]


def test_billing_checkout_requires_configured_provider() -> None:
    client, _, _, _ = _client()
    response = client.post("/v1/billing/checkout", headers={"Authorization": "Bearer test"}, json={"plan": "pro"})
    assert response.status_code == 503


def test_paid_workspace_must_use_portal_for_plan_changes() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.OWNER)
    client = TestClient(create_app(
        auth_provider=StaticAuth(context),
        billing_provider=InMemoryBillingProvider(),
    ))
    response = client.post(
        "/v1/billing/checkout",
        headers={"Authorization": "Bearer test"},
        json={"plan": "team"},
    )
    assert response.status_code == 409
    assert "billing portal" in response.json()["message"]


def test_billing_checkout_returns_provider_url_for_owner() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.FREE, WorkspaceRole.OWNER)
    client = TestClient(create_app(
        auth_provider=StaticAuth(context),
        billing_provider=InMemoryBillingProvider(),
    ))
    response = client.post("/v1/billing/checkout", headers={"Authorization": "Bearer test"}, json={"plan": "team"})
    assert response.status_code == 201
    assert response.json()["url"] == f"https://billing.test/checkout/{context.workspace_id}/team"


def test_billing_portal_is_billing_admin_only() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    client = TestClient(create_app(
        auth_provider=StaticAuth(context),
        billing_provider=InMemoryBillingProvider(),
    ))
    response = client.post("/v1/billing/portal", headers={"Authorization": "Bearer test"})
    assert response.status_code == 403


def test_billing_portal_returns_provider_url_for_billing_admin() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.BILLING_ADMIN)
    client = TestClient(create_app(
        auth_provider=StaticAuth(context),
        billing_provider=InMemoryBillingProvider(),
    ))
    response = client.post("/v1/billing/portal", headers={"Authorization": "Bearer test"})
    assert response.status_code == 201
    assert response.json()["url"] == f"https://billing.test/portal/{context.workspace_id}"


def test_free_plan_cannot_start_paid_checkout() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.FREE, WorkspaceRole.OWNER)
    client = TestClient(create_app(
        auth_provider=StaticAuth(context),
        billing_provider=InMemoryBillingProvider(),
    ))
    response = client.post("/v1/billing/checkout", headers={"Authorization": "Bearer test"}, json={"plan": "free"})
    assert response.status_code == 400


def test_free_workspace_can_start_paid_checkout() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.FREE, WorkspaceRole.OWNER)
    client = TestClient(create_app(
        auth_provider=StaticAuth(context),
        billing_provider=InMemoryBillingProvider(),
    ))
    response = client.post(
        "/v1/billing/checkout",
        headers={"Authorization": "Bearer test"},
        json={"plan": "pro"},
    )
    assert response.status_code == 201
    assert response.json()["url"] == f"https://billing.test/checkout/{context.workspace_id}/pro"


def test_checkout_rejects_same_current_plan() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.OWNER)
    client = TestClient(create_app(
        auth_provider=StaticAuth(context),
        billing_provider=InMemoryBillingProvider(),
    ))
    response = client.post(
        "/v1/billing/checkout",
        headers={"Authorization": "Bearer test"},
        json={"plan": "pro"},
    )
    assert response.status_code == 409
