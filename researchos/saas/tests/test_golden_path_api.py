from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from researchos.research_core.contracts import ResearchArtifact, ResearchResult
from researchos.saas.api import create_app
from researchos.saas.contracts import Plan, ResearchJob, ResearchJobStatus, TenantContext, WorkspaceRole
from researchos.saas.evidence_api import InMemoryResearchEvidenceStore, ResearchEvidenceRecord
from researchos.saas.store import InMemoryResearchJobStore


class StaticAuth:
    def __init__(self, context: TenantContext) -> None:
        self.context = context

    def authenticate(self, authorization: str | None, requested_workspace_id: UUID | None = None) -> TenantContext:
        if authorization != "Bearer test":
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="invalid credentials")
        if requested_workspace_id is not None and requested_workspace_id != self.context.workspace_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="workspace is not authorized")
        return self.context


def _job(workspace_id: UUID, dataset_hash: str) -> ResearchJob:
    return ResearchJob(
        id=uuid4(),
        workspace_id=workspace_id,
        dataset_version_id=uuid4(),
        workflow_id="xauusd.m1.frozen.v1",
        status=ResearchJobStatus.QUEUED,
        source_dataset_sha256=dataset_hash,
        created_by=uuid4(),
    )


def test_golden_path_result_and_evidence_are_tenant_scoped() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    other = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    jobs = InMemoryResearchJobStore()
    evidence = InMemoryResearchEvidenceStore()
    job = jobs.create(context.workspace_id, _job(context.workspace_id, "a" * 64))
    lease = jobs.claim(context.workspace_id, job.id, "test-worker", 60)
    jobs.record_result(
        context.workspace_id,
        job.id,
        lease.token,
        ResearchResult(
            "SUCCEEDED",
            "a" * 64,
            (ResearchArtifact("artifact-1", "evidence", "b" * 64),),
        ),
    )
    evidence.add(
        ResearchEvidenceRecord(
            id=uuid4(),
            workspace_id=context.workspace_id,
            research_run_id=job.id,
            artifact_id=None,
            claim="golden path evidence",
            status="proven",
            provenance={"manifest_sha256": jobs.get_result(context.workspace_id, job.id).manifest_sha256},
        )
    )

    app = create_app(
        auth_provider=StaticAuth(context),
        job_store=jobs,
        evidence_store=evidence,
    )
    client = TestClient(app)
    result = client.get(f"/v1/research-runs/{job.id}/result", headers={"Authorization": "Bearer test"})
    assert result.status_code == 200
    assert result.json()["workspace_id"] == str(context.workspace_id)
    assert result.json()["source_dataset_sha256"] == "a" * 64
    assert result.json()["manifest_sha256"]

    evidence_response = client.get(
        f"/v1/research-runs/{job.id}/evidence",
        headers={"Authorization": "Bearer test"},
    )
    assert evidence_response.status_code == 200
    assert len(evidence_response.json()) == 1

    other_client = TestClient(create_app(auth_provider=StaticAuth(other), job_store=jobs, evidence_store=evidence))
    assert other_client.get(
        f"/v1/research-runs/{job.id}/result",
        headers={"Authorization": "Bearer test"},
    ).status_code == 404
    assert other_client.get(
        f"/v1/research-runs/{job.id}/evidence",
        headers={"Authorization": "Bearer test"},
    ).json() == []


def test_result_endpoint_fails_closed_when_no_result_exists() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.VIEWER)
    jobs = InMemoryResearchJobStore()
    job = jobs.create(context.workspace_id, _job(context.workspace_id, "c" * 64))
    client = TestClient(create_app(auth_provider=StaticAuth(context), job_store=jobs))
    assert client.get(
        f"/v1/research-runs/{job.id}/result",
        headers={"Authorization": "Bearer test"},
    ).status_code == 404


def test_evidence_endpoint_fails_closed_when_store_is_unconfigured() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.VIEWER)
    client = TestClient(create_app(auth_provider=StaticAuth(context)))
    response = client.get(
        f"/v1/research-runs/{uuid4()}/evidence",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 503
