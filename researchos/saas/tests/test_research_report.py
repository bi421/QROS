from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from researchos.research_core.contracts import ResearchArtifact, ResearchResult
from researchos.saas.api import create_app
from researchos.saas.contracts import Plan, ResearchJob, ResearchJobStatus, TenantContext, WorkspaceRole
from researchos.saas.evidence_api import InMemoryResearchEvidenceStore, ResearchEvidenceRecord
from researchos.saas.research_report import build_research_report
from researchos.saas.store import InMemoryResearchJobStore


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


def _result(jobs: InMemoryResearchJobStore, workspace_id: UUID, job: ResearchJob):
    lease = jobs.claim(workspace_id, job.id, "report-test-worker", 60)
    return jobs.record_result(
        workspace_id,
        job.id,
        lease.token,
        ResearchResult(
            "SUCCEEDED",
            job.source_dataset_sha256,
            (
                ResearchArtifact("artifact-z", "finding", "b" * 64),
                ResearchArtifact("artifact-a", "evidence", "c" * 64),
            ),
        ),
    )


def test_report_is_byte_deterministic_and_preserves_governed_status() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    jobs = InMemoryResearchJobStore()
    evidence = InMemoryResearchEvidenceStore()
    job = jobs.create(context.workspace_id, _job(context.workspace_id, "a" * 64))
    record = _result(jobs, context.workspace_id, job)
    evidence.add(
        ResearchEvidenceRecord(
            id=uuid4(),
            workspace_id=context.workspace_id,
            research_run_id=job.id,
            artifact_id=None,
            claim="stored evidence claim",
            status="proven",
            provenance={"manifest_sha256": record.manifest_sha256},
        )
    )

    rows = evidence.list_for_run(context.workspace_id, job.id)
    first = build_research_report(record, rows)
    second = build_research_report(record, list(reversed(rows)))

    assert first.markdown == second.markdown
    assert first.report_sha256 == second.report_sha256
    assert first.status == "SUCCEEDED"
    assert record.manifest_sha256 in first.markdown
    assert "does not infer causality" in first.markdown


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


def test_report_endpoint_is_tenant_scoped_and_contains_lineage_hashes() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    other = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    jobs = InMemoryResearchJobStore()
    evidence = InMemoryResearchEvidenceStore()
    job = jobs.create(context.workspace_id, _job(context.workspace_id, "d" * 64))
    record = _result(jobs, context.workspace_id, job)
    evidence.add(
        ResearchEvidenceRecord(
            id=uuid4(),
            workspace_id=context.workspace_id,
            research_run_id=job.id,
            artifact_id=None,
            claim="customer-visible lineage",
            status="proven",
            provenance={"manifest_sha256": record.manifest_sha256},
        )
    )

    client = TestClient(
        create_app(
            auth_provider=StaticAuth(context),
            job_store=jobs,
            evidence_store=evidence,
        )
    )
    response = client.get(
        f"/v1/research-runs/{job.id}/report",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["schema"] == "qros-research-report.v1"
    assert body["workspace_id"] == str(context.workspace_id)
    assert body["research_run_id"] == str(job.id)
    assert body["source_dataset_sha256"] == "d" * 64
    assert body["manifest_sha256"] == record.manifest_sha256
    assert body["report_sha256"]
    assert "customer-visible lineage" in body["markdown"]

    other_client = TestClient(
        create_app(
            auth_provider=StaticAuth(other),
            job_store=jobs,
            evidence_store=evidence,
        )
    )
    assert other_client.get(
        f"/v1/research-runs/{job.id}/report",
        headers={"Authorization": "Bearer test"},
    ).status_code == 404


def test_report_endpoint_fails_closed_without_result_or_evidence_store() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.VIEWER)
    jobs = InMemoryResearchJobStore()
    job = jobs.create(context.workspace_id, _job(context.workspace_id, "e" * 64))

    client = TestClient(create_app(auth_provider=StaticAuth(context), job_store=jobs))

    # A missing result is a resource absence, so it must remain a 404.
    assert client.get(
        f"/v1/research-runs/{uuid4()}/report",
        headers={"Authorization": "Bearer test"},
    ).status_code == 404

    # Once a result exists, an unconfigured evidence store is an unavailable
    # dependency and must fail closed with 503.
    _result(jobs, context.workspace_id, job)
    assert client.get(
        f"/v1/research-runs/{job.id}/report",
        headers={"Authorization": "Bearer test"},
    ).status_code == 503
