"""P0 real-database tenant isolation and lineage tests.

Run explicitly with:
    pytest researchos/saas/tests/test_tenant_isolation_real.py --real-db -v

These tests never replace Supabase RLS/auth with mocks.  The API uses the real
Supabase JWT verifier and service-role persistence boundary; direct PostgREST
operations use each tenant's real JWT.
"""

from __future__ import annotations

from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from researchos.claims.claim import ResearchClaim, ResearchPlan
from researchos.saas.runtime import build_production_app
from researchos.saas.tests.conftest import RealTenant, RealTenantPair


@pytest.fixture
def resources(real_tenants: RealTenantPair) -> dict[str, object]:
    service = real_tenants.service
    a = real_tenants.a
    b = real_tenants.b

    dataset_a = uuid4()
    version_a = uuid4()
    job_a = uuid4()
    evidence_a = uuid4()
    finding_a = uuid4()
    validation_a = uuid4()
    artifact_a = uuid4()

    digest = sha256(f"tenant-a-{dataset_a}".encode()).hexdigest()
    service.table("dataset").insert(
        {
            "id": str(dataset_a),
            "workspace_id": str(a.workspace_id),
            "name": "real-tenant-a-dataset",
            "created_by": str(a.user_id),
        }
    ).execute()
    service.table("dataset_version").insert(
        {
            "id": str(version_a),
            "dataset_id": str(dataset_a),
            "version_no": 1,
            "content_sha256": digest,
            "storage_path": f"tenant/{a.workspace_id}/datasets/{digest}/1/",
            "byte_size": 32,
            "created_by": str(a.user_id),
        }
    ).execute()

    plan = ResearchPlan(
        hypothesis="tenant isolation remains intact",
        sample_definition="one synthetic release fixture",
        features=("feature",),
        labels=("label",),
        train_validation_test="all",
        exclusions=(),
        costs_slippage="none",
        statistical_tests=("none",),
        metrics=("count",),
        stopping_rules=("none",),
        multiple_testing_policy="none",
        replication_policy="none",
    )
    claim = ResearchClaim(
        statement="Tenant A claim must remain private",
        workspace_id=str(a.workspace_id),
        creator=str(a.user_id),
        research_id="tenant-isolation-real",
    )
    claim.plan = plan
    claim.plan_hash = plan.content_hash
    claim.evidence_state = "CANDIDATE"
    service.table("research_claim").insert(
        {
            "id": claim.id,
            "workspace_id": str(a.workspace_id),
            "statement": claim.statement,
            "claim_type": claim.claim_type.value,
            "evidence_state": claim.evidence_state.value,
            "version": claim.version,
            "parent_claim_id": claim.parent_claim_id,
            "research_id": claim.research_id,
            "creator": claim.creator,
            "plan_hash": claim.plan_hash,
            "plan_locked_at": None,
            "claim_hash": claim.claim_hash,
            "payload": claim.to_dict(),
        }
    ).execute()

    service.table("research_run").insert(
        {
            "id": str(job_a),
            "workspace_id": str(a.workspace_id),
            "dataset_version_id": str(version_a),
            "workflow_id": "tenant-isolation-real",
            "status": "queued",
            "created_by": str(a.user_id),
            "source_dataset_sha256": digest,
            "claim_id": claim.id,
            "plan_hash": plan.content_hash,
        }
    ).execute()

    service.table("artifact").insert(
        {
            "id": str(artifact_a),
            "workspace_id": str(a.workspace_id),
            "research_run_id": str(job_a),
            "kind": "evidence",
            "content_sha256": digest,
            "storage_path": f"tenant/{a.workspace_id}/evidence/{digest}",
            "byte_size": 32,
        }
    ).execute()

    service.table("evidence").insert(
        {
            "id": str(evidence_a),
            "workspace_id": str(a.workspace_id),
            "research_run_id": str(job_a),
            "artifact_id": str(artifact_a),
            "claim": "tenant A evidence",
            "status": "verified",
            "provenance": {"test": "real-tenant-isolation"},
        }
    ).execute()

    # Finding is intentionally inserted through the service role because its
    # production write path is governed by validation.  The test exercises the
    # RLS read/update/delete boundary using tenant B's real JWT.
    service.table("research_validation").insert(
        {
            "id": str(validation_a),
            "workspace_id": str(a.workspace_id),
            "research_run_id": str(job_a),
            "result_manifest_sha256": digest,
            "claim_id": claim.id,
            "plan_hash": plan.content_hash,
            "validation_sha256": digest,
            "status": "VALIDATED",
            "metrics": {"score": 1.0},
            "contract_version": "1.0.0",
        }
    ).execute()
    service.table("research_finding").insert(
        {
            "id": str(finding_a),
            "workspace_id": str(a.workspace_id),
            "research_run_id": str(job_a),
            "validation_id": str(validation_a),
            "result_manifest_sha256": digest,
            "validation_sha256": digest,
            "claim_id": claim.id,
            "plan_hash": plan.content_hash,
            "finding_sha256": digest,
            "status": "VALIDATED",
            "payload": {"test": "tenant-a"},
            "contract_version": "1.0.0",
        }
    ).execute()

    return {
        "dataset": dataset_a,
        "version": version_a,
        "job": job_a,
        "evidence": evidence_a,
        "finding": finding_a,
        "claim": claim.id,
        "plan_hash": plan.content_hash,
        "digest": digest,
        "a": a,
        "b": b,
    }


def _assert_structured_failure(response) -> None:
    assert response.status_code in {403, 404}, response.text
    payload = response.json()
    assert payload["code"] in {"forbidden", "not_found", "TENANT_ISOLATION_VIOLATION"}
    assert payload.get("request_id")
    assert payload.get("correlation_id")


@pytest.fixture
def api_client(real_tenants: RealTenantPair) -> TestClient:
    return TestClient(build_production_app())


def _headers(tenant: RealTenant, *, key: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {tenant.access_token}",
        "X-Workspace-ID": str(tenant.workspace_id),
    }
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


@pytest.mark.parametrize(
    ("resource", "endpoint"),
    [
        ("dataset", lambda r: f"/v1/datasets/{r['dataset']}"),
        ("job", lambda r: f"/v1/research-runs/{r['job']}"),
        ("finding", lambda r: f"/v1/research-runs/{r['job']}/finding"),
    ],
)
def test_tenant_b_cannot_read_tenant_a_resource(
    api_client: TestClient, resources: dict[str, object], resource: str, endpoint
) -> None:
    b = resources["b"]
    assert isinstance(b, RealTenant)
    response = api_client.get(endpoint(resources), headers=_headers(b))
    _assert_structured_failure(response)


def test_tenant_b_cannot_read_tenant_a_version_or_evidence(
    api_client: TestClient, resources: dict[str, object]
) -> None:
    b = resources["b"]
    assert isinstance(b, RealTenant)

    response = api_client.get(
        f"/v1/datasets/{resources['dataset']}/versions/{resources['version']}",
        headers=_headers(b),
    )
    _assert_structured_failure(response)

    response = api_client.get(
        f"/v1/research-runs/{resources['job']}/evidence",
        headers=_headers(b),
    )
    assert response.status_code == 200
    assert response.json() == []


def test_tenant_b_list_never_contains_tenant_a_resource(
    api_client: TestClient, resources: dict[str, object]
) -> None:
    b = resources["b"]
    assert isinstance(b, RealTenant)

    datasets = api_client.get("/v1/datasets", headers=_headers(b))
    assert datasets.status_code == 200
    assert all(item["id"] != str(resources["dataset"]) for item in datasets.json()["items"])

    jobs = api_client.get("/v1/research-runs", headers=_headers(b))
    assert jobs.status_code == 200
    assert all(item["id"] != str(resources["job"]) for item in jobs.json()["items"])


def test_tenant_b_cannot_update_or_delete_tenant_a_rows_directly(
    real_tenants: RealTenantPair, resources: dict[str, object]
) -> None:
    b = real_tenants.b
    for table, key in (
        ("dataset", "dataset"),
        ("dataset_version", "version"),
        ("research_run", "job"),
        ("evidence", "evidence"),
        ("research_finding", "finding"),
    ):
        row_id = str(resources[key])
        update = b.client.table(table).update({"updated_at": "now()"}).eq("id", row_id).execute()
        delete = b.client.table(table).delete().eq("id", row_id).execute()
        assert not update.data, f"{table} UPDATE crossed tenant boundary: {update.data}"
        assert not delete.data, f"{table} DELETE crossed tenant boundary: {delete.data}"


def test_direct_supabase_jwt_cannot_read_tenant_a_rows(
    real_tenants: RealTenantPair, resources: dict[str, object]
) -> None:
    b = real_tenants.b
    for table, key in (
        ("dataset", "dataset"),
        ("dataset_version", "version"),
        ("research_run", "job"),
        ("evidence", "evidence"),
        ("research_finding", "finding"),
    ):
        response = b.client.table(table).select("id").eq("id", str(resources[key])).execute()
        assert response.data == [], f"{table} leaked tenant A row to tenant B JWT"


def test_idempotency_key_is_workspace_scoped(
    api_client: TestClient, resources: dict[str, object]
) -> None:
    a = resources["a"]
    b = resources["b"]
    assert isinstance(a, RealTenant)
    assert isinstance(b, RealTenant)

    key = f"same-key-{uuid4().hex}"
    first = api_client.post(
        "/v1/research-runs",
        headers=_headers(a, key=key),
        json={"dataset_version_id": str(resources["version"])},
    )
    second = api_client.post(
        "/v1/research-runs",
        headers=_headers(b, key=key),
        json={"dataset_version_id": str(resources["version"])},
    )
    assert first.status_code in {201, 202}
    assert second.status_code in {201, 202}
    assert first.json()["id"] != second.json()["id"]


def test_lineage_graph_isolation(
    api_client: TestClient, resources: dict[str, object]
) -> None:
    b = resources["b"]
    assert isinstance(b, RealTenant)

    response = api_client.get(
        f"/v1/research-claims/{resources['claim']}/evidence-graph",
        headers=_headers(b),
    )
    assert response.status_code == 200
    assert response.json() == []

    claims = b.client.table("research_claim").select("id").eq("id", resources["claim"]).execute()
    assert claims.data == []

    runs = b.client.table("research_run").select("id,claim_id,plan_hash").eq("id", str(resources["job"])).execute()
    assert runs.data == []

    evidence = b.client.table("evidence").select("id").eq("research_run_id", str(resources["job"])).execute()
    assert evidence.data == []
