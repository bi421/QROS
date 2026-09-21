from uuid import UUID, uuid4
import hashlib

from fastapi.testclient import TestClient

from researchos.research_core.contracts import ResearchArtifact, ResearchResult
from researchos.saas.api import create_app
from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole
from researchos.saas.datasets import InMemoryDatasetStorage, InMemoryDatasetStore
from researchos.saas.finding import ResearchFindingRecord
from researchos.saas.finding_api import InMemoryResearchFindingStore
from researchos.saas.store import InMemoryResearchJobStore
from researchos.saas.validation import ResearchValidationRecord
from researchos.saas.validation_api import InMemoryResearchValidationStore


class _Auth:
    def __init__(self, context: TenantContext) -> None:
        self.context = context

    def authenticate(self, authorization: str | None, requested_workspace_id=None) -> TenantContext:
        assert authorization == "Bearer test"
        return self.context


def _app(context: TenantContext, jobs, validations, findings) -> TestClient:
    return TestClient(create_app(
        auth_provider=_Auth(context),
        job_store=jobs,
        validation_store=validations,
        finding_store=findings,
        dataset_store=InMemoryDatasetStore(),
        dataset_storage=InMemoryDatasetStorage(),
    ))


def _run(client: TestClient, context: TenantContext, jobs: InMemoryResearchJobStore) -> tuple[UUID, object]:
    uploaded = client.post(
        "/v1/datasets",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "upload"},
        data={"name": "boundary"},
        files={"file": ("boundary.csv", b"x", "text/csv")},
    )
    assert uploaded.status_code == 201
    response = client.post(
        "/v1/research-runs",
        headers={"Authorization": "Bearer test", "Idempotency-Key": "run"},
        json={"dataset_version_id": uploaded.json()["version"]["id"]},
    )
    assert response.status_code == 202
    job_id = UUID(response.json()["id"])
    lease = jobs.claim(context.workspace_id, job_id, "test", 60)
    jobs.record_result(context.workspace_id, job_id, lease.token, ResearchResult(
        status="SUCCEEDED",
        source_dataset_sha256=hashlib.sha256(b"x").hexdigest(),
        artifacts=(ResearchArtifact("result", "result", "1" * 64),),
    ))
    result = jobs.get_result(context.workspace_id, job_id)
    assert result is not None
    return job_id, result


def test_validation_and_finding_http_boundaries_fail_closed() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    jobs = InMemoryResearchJobStore()
    validations = InMemoryResearchValidationStore()
    findings = InMemoryResearchFindingStore()
    client = _app(context, jobs, validations, findings)
    job_id, result = _run(client, context, jobs)

    missing = client.post(
        f"/v1/research-runs/{job_id}/finding",
        headers={"Authorization": "Bearer test"},
        json={"validation_sha256": "a" * 64, "payload": {"finding": "x"}},
    )
    assert missing.status_code == 404

    payload = {"metrics": {"brier_improvement": 0.1}, "gate": "PASS"}
    validation = ResearchValidationRecord(
        id=uuid4(), workspace_id=context.workspace_id, research_run_id=job_id,
        result_manifest_sha256=result.manifest_sha256, claim_id=None, plan_hash=None,
        validation_sha256=ResearchValidationRecord.compute_validation_sha256(payload),
        status="VALIDATED", metrics={"brier_improvement": 0.1},
    )
    validations.create(validation)

    wrong = client.post(
        f"/v1/research-runs/{job_id}/finding",
        headers={"Authorization": "Bearer test"},
        json={"validation_sha256": "b" * 64, "payload": {"finding": "x"}},
    )
    assert wrong.status_code == 409

    created = client.post(
        f"/v1/research-runs/{job_id}/finding",
        headers={"Authorization": "Bearer test"},
        json={"validation_sha256": validation.validation_sha256, "payload": {"finding": "validated"}},
    )
    assert created.status_code == 201
    assert created.json()["validation_id"] == str(validation.id)
    assert created.json()["result_manifest_sha256"] == result.manifest_sha256

    fetched = client.get(
        f"/v1/research-runs/{job_id}/finding",
        headers={"Authorization": "Bearer test"},
    )
    assert fetched.status_code == 200
    assert fetched.json()["finding_sha256"] == created.json()["finding_sha256"]


def test_validation_and_finding_reads_are_tenant_scoped() -> None:
    owner = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    other = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    jobs = InMemoryResearchJobStore()
    validations = InMemoryResearchValidationStore()
    findings = InMemoryResearchFindingStore()
    owner_client = _app(owner, jobs, validations, findings)
    job_id, result = _run(owner_client, owner, jobs)
    payload = {"metrics": {"brier_improvement": 0.1}}
    validation = ResearchValidationRecord(
        id=uuid4(), workspace_id=owner.workspace_id, research_run_id=job_id,
        result_manifest_sha256=result.manifest_sha256, claim_id=None, plan_hash=None,
        validation_sha256=ResearchValidationRecord.compute_validation_sha256(payload),
        status="VALIDATED", metrics={"brier_improvement": 0.1},
    )
    validations.create(validation)
    finding_payload = {"finding": "validated"}
    findings.create(ResearchFindingRecord(
        id=uuid4(), workspace_id=owner.workspace_id, research_run_id=job_id,
        validation_id=validation.id, result_manifest_sha256=result.manifest_sha256,
        validation_sha256=validation.validation_sha256, claim_id=None, plan_hash=None,
        finding_sha256=ResearchFindingRecord.compute_finding_sha256(finding_payload),
        status="VALIDATED", payload=finding_payload,
    ))
    other_client = _app(other, jobs, validations, findings)
    assert other_client.get(f"/v1/research-runs/{job_id}/validation", headers={"Authorization": "Bearer test"}).status_code == 404
    assert other_client.get(f"/v1/research-runs/{job_id}/finding", headers={"Authorization": "Bearer test"}).status_code == 404
