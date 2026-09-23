"""Real Supabase tenant-isolation integration tests.

These tests intentionally use two authenticated Supabase users and the real
Postgres RLS boundary. No mock RLS or in-memory persistence is used.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Generator
from uuid import UUID, uuid4

import pytest

from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole, ResearchJob, ResearchJobStatus
from researchos.saas.datasets import Dataset, DatasetVersion, SupabaseDatasetStore
from researchos.saas.finding import ResearchFindingRecord
from researchos.saas.idempotency import IdempotencyRecord, SupabaseIdempotencyStore
from researchos.saas.supabase_finding_store import SupabaseResearchFindingStore
from researchos.saas.supabase_job_store import SupabaseResearchJobStore

pytestmark = pytest.mark.real_db


@dataclass(frozen=True)
class RealTenant:
    user_id: UUID
    workspace_id: UUID
    email: str
    password: str
    client: object
    context: TenantContext


@dataclass(frozen=True)
class Fixtures:
    a: RealTenant
    b: RealTenant
    dataset: Dataset
    version: DatasetVersion
    job_id: UUID
    evidence_id: UUID
    finding: ResearchFindingRecord
    idempotency_key: str


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.fail(f"missing required real-db environment variable: {name}")
    return value


def _client(url: str, key: str) -> object:
    from supabase import create_client
    return create_client(url, key)


def _sign_in(url: str, anon_key: str, email: str, password: str) -> object:
    client = _client(url, anon_key)
    client.auth.sign_in_with_password({"email": email, "password": password})
    return client


def _error_code(exc: BaseException) -> str:
    return str(getattr(exc, "code", ""))


def _assert_rls_denied_or_empty(callable_: object) -> None:
    try:
        result = callable_()
    except Exception as exc:
        assert _error_code(exc) in {"42501", "PGRST301", "PGRST116"} or "permission" in str(exc).lower()
        return
    rows = getattr(result, "data", None)
    assert not rows, "cross-tenant RLS query returned tenant-owned rows"


def _sha(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


@pytest.fixture(scope="session")
def fixtures(real_db: bool) -> Generator[Fixtures, None, None]:
    del real_db
    url = os.getenv("SUPABASE_REAL_DB_URL", os.getenv("SUPABASE_URL"))
    service_key = os.getenv("SUPABASE_REAL_DB_SERVICE_ROLE_KEY", os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    anon_key = os.getenv("SUPABASE_REAL_DB_ANON_KEY", os.getenv("SUPABASE_ANON_KEY", service_key))
    password = _required_env("QROS_REAL_DB_TEST_PASSWORD")
    if not url or not service_key or not anon_key:
        pytest.fail("real-db requires Supabase URL, service-role key, and anon key")

    service = _client(url, service_key)
    tenants: list[RealTenant] = []
    workspace_ids: list[UUID] = []
    user_ids: list[UUID] = []

    try:
        for label in ("tenant_a", "tenant_b"):
            email = f"qros-tenant-isolation-{label}-{uuid4()}@example.invalid"
            user_response = service.auth.admin.create_user(
                {"email": email, "password": password, "email_confirm": True}
            )
            user_id = UUID(str(user_response.user.id))
            workspace = service.table("workspace").insert({"name": label}).select("id").single().execute()
            workspace_id = UUID(str(workspace.data["id"]))
            service.table("workspace_member").insert(
                {"workspace_id": str(workspace_id), "user_id": str(user_id), "role": "researcher"}
            ).execute()
            tenants.append(
                RealTenant(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    email=email,
                    password=password,
                    client=_sign_in(url, anon_key, email, password),
                    context=TenantContext(user_id, workspace_id, Plan.PRO, WorkspaceRole.RESEARCHER),
                )
            )
            workspace_ids.append(workspace_id)
            user_ids.append(user_id)

        a, b = tenants
        dataset = Dataset(uuid4(), a.workspace_id, "tenant-a-dataset", a.user_id)
        dataset_store = SupabaseDatasetStore(service)
        dataset_store.create_dataset(a.workspace_id, dataset)
        digest = _sha("tenant-a-dataset")
        version = DatasetVersion(
            uuid4(), dataset.id, 1, digest,
            f"{a.workspace_id}/datasets/{dataset.id}/sha256/{digest}", 16, a.user_id
        )
        dataset_store.create_version(a.workspace_id, version)

        job = ResearchJob(
            uuid4(), a.workspace_id, version.id, "xauusd_m1_frozen_research_v1",
            ResearchJobStatus.QUEUED, digest, a.user_id
        )
        SupabaseResearchJobStore(service).create(a.workspace_id, job)

        manifest = _sha("manifest")
        service.table("research_run_result").insert({
            "workspace_id": str(a.workspace_id), "research_run_id": str(job.id),
            "source_dataset_sha256": digest, "status": "SUCCEEDED",
            "manifest_sha256": manifest, "failures": [],
        }).execute()

        validation_id = uuid4()
        validation_sha = _sha("validation")
        validation = service.rpc("create_research_validation", {
            "p_id": str(validation_id), "p_workspace_id": str(a.workspace_id),
            "p_research_run_id": str(job.id), "p_result_manifest_sha256": manifest,
            "p_claim_id": None, "p_plan_hash": None, "p_validation_sha256": validation_sha,
            "p_status": "VALIDATED", "p_metrics": {"integration": True},
            "p_contract_version": "1.0.0",
        }).execute()
        assert validation.data

        payload = {"tenant": "tenant_a", "integration": True}
        finding = ResearchFindingRecord(
            uuid4(), a.workspace_id, job.id, validation_id, manifest, validation_sha,
            None, None, ResearchFindingRecord.compute_finding_sha256(payload),
            "VALIDATED", payload
        )
        SupabaseResearchFindingStore(service).create(finding)

        evidence_id = uuid4()
        service.table("evidence").insert({
            "id": str(evidence_id), "workspace_id": str(a.workspace_id),
            "research_run_id": str(job.id),
            "claim": "tenant-isolation integration evidence", "status": "proven",
            "provenance": {
                "feeds": [version.id.hex], "produces": [job.id.hex],
                "validates": [validation_id.hex], "derives": [finding.id.hex],
                "trains": [], "contradicts": [], "replicates": [],
            },
        }).execute()

        key = f"tenant-isolation-{uuid4()}"
        for tenant, fingerprint in ((a, _sha("request-a")), (b, _sha("request-b"))):
            SupabaseIdempotencyStore(service).put(
                IdempotencyRecord(
                    tenant.workspace_id, key, fingerprint, 202,
                    {"tenant": str(tenant.workspace_id)}
                )
            )

        return Fixtures(a, b, dataset, version, job.id, evidence_id, finding, key)
    except Exception:
        for workspace_id in workspace_ids:
            service.table("workspace").delete().eq("id", str(workspace_id)).execute()
        for user_id in user_ids:
            try:
                service.auth.admin.delete_user(str(user_id))
            except Exception:
                pass
        raise


def test_direct_rls_blocks_every_tenant_a_resource_for_tenant_b(fixtures: Fixtures) -> None:
    b = fixtures.b.client
    for table, resource_id in (
        ("dataset", fixtures.dataset.id), ("research_run", fixtures.job_id),
        ("evidence", fixtures.evidence_id), ("research_validation", fixtures.finding.validation_id),
        ("research_finding", fixtures.finding.id), ("research_run_result", fixtures.job_id),
    ):
        query = b.table(table).select("*").eq("id", str(resource_id))
        _assert_rls_denied_or_empty(lambda query=query: query.limit(1).execute())

    for table in ("dataset_version", "research_run_artifact"):
        query = b.table(table).select("*").eq(
            "id" if table == "dataset_version" else "research_run_id",
            str(fixtures.version.id if table == "dataset_version" else fixtures.job_id),
        )
        _assert_rls_denied_or_empty(lambda query=query: query.limit(1).execute())

    query = b.table("api_idempotency").select("*").eq("key", fixtures.idempotency_key)
    _assert_rls_denied_or_empty(lambda: query.limit(1).execute())


def test_tenant_b_cannot_list_tenant_a_rows_via_rls(fixtures: Fixtures) -> None:
    b = fixtures.b.client
    for table in ("dataset", "research_run", "evidence", "research_validation", "research_finding", "research_run_result"):
        query = b.table(table).select("*").eq("workspace_id", str(fixtures.a.workspace_id))
        _assert_rls_denied_or_empty(lambda query=query: query.execute())
    for table, column, value in (
        ("dataset_version", "dataset_id", fixtures.dataset.id),
        ("research_run_artifact", "research_run_id", fixtures.job_id),
    ):
        query = b.table(table).select("*").eq(column, str(value))
        _assert_rls_denied_or_empty(lambda query=query: query.execute())


def test_tenant_b_cannot_mutate_or_delete_tenant_a_rows_via_rls(fixtures: Fixtures) -> None:
    b = fixtures.b.client
    for table, resource_id in (
        ("dataset", fixtures.dataset.id), ("research_run", fixtures.job_id),
        ("evidence", fixtures.evidence_id), ("research_finding", fixtures.finding.id),
    ):
        update = {"name": "cross-tenant"} if table == "dataset" else {}
        _assert_rls_denied_or_empty(
            lambda table=table, resource_id=resource_id, update=update:
            b.table(table).update(update).eq("id", str(resource_id)).execute()
        )
        _assert_rls_denied_or_empty(
            lambda table=table, resource_id=resource_id:
            b.table(table).delete().eq("id", str(resource_id)).execute()
        )


def test_same_idempotency_key_isolated_by_workspace(fixtures: Fixtures) -> None:
    a_record = SupabaseIdempotencyStore(fixtures.a.client).get(fixtures.a.workspace_id, fixtures.idempotency_key)
    b_record = SupabaseIdempotencyStore(fixtures.b.client).get(fixtures.b.workspace_id, fixtures.idempotency_key)
    assert a_record is not None and b_record is not None
    assert a_record.response_body != b_record.response_body
    assert a_record.request_fingerprint != b_record.request_fingerprint

    cross = fixtures.b.client.table("api_idempotency").select("*").eq(
        "workspace_id", str(fixtures.a.workspace_id)
    ).eq("key", fixtures.idempotency_key)
    _assert_rls_denied_or_empty(lambda: cross.limit(1).execute())


def test_all_declared_lineage_relations_are_tenant_bound(fixtures: Fixtures) -> None:
    row = fixtures.a.client.table("evidence").select("workspace_id,provenance").eq(
        "id", str(fixtures.evidence_id)
    ).single().execute()
    assert UUID(str(row.data["workspace_id"])) == fixtures.a.workspace_id
    assert set(row.data["provenance"]) == {
        "feeds", "produces", "validates", "derives", "trains", "contradicts", "replicates"
    }
    cross = fixtures.b.client.table("evidence").select("*").eq("id", str(fixtures.evidence_id))
    _assert_rls_denied_or_empty(lambda: cross.limit(1).execute())


def test_cross_tenant_api_access_is_404_and_has_request_id(fixtures: Fixtures) -> None:
    from fastapi.testclient import TestClient
    from researchos.saas.api import create_app
    from researchos.saas.datasets import SupabaseDatasetStorage

    class StaticAuth:
        def __init__(self, context: TenantContext) -> None:
            self.context = context

        def authenticate(self, authorization: str | None, requested_workspace_id: UUID | None = None) -> TenantContext:
            del authorization
            if requested_workspace_id is not None and requested_workspace_id != self.context.workspace_id:
                from fastapi import HTTPException
                raise HTTPException(status_code=403, detail="workspace is not authorized")
            return self.context

    url = _required_env("SUPABASE_REAL_DB_URL")
    service = _client(url, _required_env("SUPABASE_REAL_DB_SERVICE_ROLE_KEY"))
    app = create_app(
        auth_provider=StaticAuth(fixtures.b.context),
        dataset_store=SupabaseDatasetStore(service),
        dataset_storage=SupabaseDatasetStorage(service),
    )
    with TestClient(app) as client:
        response = client.get(
            f"/v1/datasets/{fixtures.dataset.id}/versions/{fixtures.version.id}/download",
            headers={"X-Request-ID": "tenant-isolation-cross-read"},
        )
    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "tenant-isolation-cross-read"
    assert response.json()["error"]["code"] == "NOT_FOUND"
