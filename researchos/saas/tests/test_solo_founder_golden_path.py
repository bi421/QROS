"""Solo-founder acceptance test for the governed XAUUSD SaaS delivery path.

The scientific pipeline is replaced with a deterministic artifact producer so
this test isolates upload -> immutable dataset version -> API run -> queue ->
governed worker -> result/report retrieval. Scientific pipeline correctness is
covered separately by its own tests and real-data evidence gates.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from researchos.research_core.contracts import FROZEN_XAUUSD_M1_WORKFLOW
from researchos.research_core.runner import PipelineArtifact
from researchos.saas.api import create_app
from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole
from researchos.saas.datasets import InMemoryDatasetStorage, InMemoryDatasetStore
from researchos.saas.evidence_api import InMemoryResearchEvidenceStore
from researchos.saas.queue import InMemoryResearchJobQueue
from researchos.saas.research_executor import GovernedResearchExecutor
from researchos.saas.store import InMemoryResearchJobStore
from researchos.saas.worker import ResearchWorker


class StaticAuth:
    def __init__(self, context: TenantContext) -> None:
        self.context = context

    def authenticate(self, authorization: str | None) -> TenantContext:
        if authorization != "Bearer solo-founder-test":
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="invalid credentials")
        return self.context


def test_solo_founder_golden_path_upload_queue_worker_result_and_report(monkeypatch) -> None:
    context = TenantContext(
        user_id=uuid4(),
        workspace_id=uuid4(),
        plan=Plan.PRO,
        role=WorkspaceRole.OWNER,
    )
    raw = (
        b"timestamp,open,high,low,close,tick_volume\n"
        b"2026-01-01T00:00:00Z,2000,2002,1998,2001,10\n"
    )
    artifact_bytes = b'{"contract":"fixture-only","scientific_status":"NOT_EVALUATED"}'
    artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()

    class DeterministicPipeline:
        def __init__(self, resolver) -> None:
            self._resolver = resolver

        def __call__(self, request):
            # Exercise the executor's dataset identity/hash-bound resolver.
            assert self._resolver(request) == raw
            yield PipelineArtifact(
                artifact_id=artifact_sha256,
                kind="solo_founder_golden_path_fixture",
                content=artifact_bytes,
            )

    # This is deliberately a SaaS integration test, not a scientific edge test.
    monkeypatch.setattr(
        "researchos.saas.research_executor.FrozenXauusdM1Pipeline",
        DeterministicPipeline,
    )

    jobs = InMemoryResearchJobStore()
    datasets = InMemoryDatasetStore()
    storage = InMemoryDatasetStorage()
    queue = InMemoryResearchJobQueue()
    evidence = InMemoryResearchEvidenceStore()
    client = TestClient(
        create_app(
            auth_provider=StaticAuth(context),
            job_store=jobs,
            dataset_store=datasets,
            dataset_storage=storage,
            job_queue=queue,
            evidence_store=evidence,
        )
    )
    headers = {"Authorization": "Bearer solo-founder-test"}

    uploaded = client.post(
        "/v1/datasets",
        headers={**headers, "Idempotency-Key": "golden-path-dataset"},
        data={"name": "xauusd-m1-golden-path"},
        files={"file": ("xauusd_m1_mt5.csv", BytesIO(raw), "text/csv")},
    )
    assert uploaded.status_code == 201, uploaded.text
    dataset = uploaded.json()
    version = dataset["version"]
    expected_source_sha256 = hashlib.sha256(raw).hexdigest()
    assert version["content_sha256"] == expected_source_sha256
    assert storage.download(version["storage_path"]) == raw

    created = client.post(
        "/v1/research-runs",
        headers={**headers, "Idempotency-Key": "golden-path-run"},
        json={
            "dataset_version_id": version["id"],
            "workflow_id": FROZEN_XAUUSD_M1_WORKFLOW,
        },
    )
    assert created.status_code == 202, created.text
    run = created.json()
    run_id = UUID(run["id"])
    assert run["status"] == "queued"
    assert run["workspace_id"] == str(context.workspace_id)
    assert len(queue.messages) == 1

    # A duplicate API submission must replay the same run without a second job.
    replay = client.post(
        "/v1/research-runs",
        headers={**headers, "Idempotency-Key": "golden-path-run"},
        json={
            "dataset_version_id": version["id"],
            "workflow_id": FROZEN_XAUUSD_M1_WORKFLOW,
        },
    )
    assert replay.status_code == 202, replay.text
    assert replay.json()["id"] == run["id"]
    assert len(queue.messages) == 1

    message = queue.receive()
    assert message is not None
    assert message.workspace_id == context.workspace_id
    assert message.research_run_id == run_id

    executor = GovernedResearchExecutor(jobs, datasets, storage, context.workspace_id)
    result = ResearchWorker(jobs, executor).run_once(
        context.workspace_id,
        run_id,
        request_id="solo-founder-golden-path",
    )
    assert result.status == "SUCCEEDED"
    assert result.source_dataset_sha256 == expected_source_sha256
    assert len(result.artifacts) == 1
    assert result.artifacts[0].content_sha256 == artifact_sha256
    queue.ack(message.message_id)
    assert queue.messages == []

    final_run = client.get(f"/v1/research-runs/{run_id}", headers=headers)
    assert final_run.status_code == 200
    assert final_run.json()["status"] == "succeeded"

    result_response = client.get(f"/v1/research-runs/{run_id}/result", headers=headers)
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["status"] == "SUCCEEDED"
    assert result_payload["source_dataset_sha256"] == expected_source_sha256
    assert result_payload["artifacts"][0]["content_sha256"] == artifact_sha256
    assert result_payload["manifest_sha256"]

    report_response = client.get(f"/v1/research-runs/{run_id}/report", headers=headers)
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["schema"] == "qros-research-report.v1"
    assert report["source_dataset_sha256"] == expected_source_sha256
    assert report["manifest_sha256"] == result_payload["manifest_sha256"]
    assert report["report_sha256"]
    assert "solo_founder_golden_path_fixture" in report["markdown"]
    assert "does not infer causality, profitability" in report["markdown"]

    repeated_report = client.get(f"/v1/research-runs/{run_id}/report", headers=headers)
    assert repeated_report.status_code == 200
    assert repeated_report.json()["report_sha256"] == report["report_sha256"]
