from uuid import uuid4

import pytest

from researchos.research_core.contracts import ResearchArtifact, ResearchResult
from researchos.saas.contracts import ResearchJob, ResearchJobStatus
from researchos.saas.store import InMemoryResearchJobStore
from researchos.saas.worker import ResearchWorker


class StubExecutor:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def execute(self, job_id):
        self.calls += 1
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


def _job(workspace_id):
    return ResearchJob(
        id=uuid4(),
        workspace_id=workspace_id,
        dataset_version_id=uuid4(),
        workflow_id="xauusd_m1_frozen_research_v1",
        status=ResearchJobStatus.QUEUED,
    )


def _result(status="SUCCEEDED"):
    artifacts = (
        (ResearchArtifact("artifact-1", "evidence", "1" * 64),)
        if status == "SUCCEEDED"
        else ()
    )
    return ResearchResult(
        status=status,
        source_dataset_sha256="0" * 64,
        artifacts=artifacts,
    )


def test_worker_moves_queued_job_to_succeeded():
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(_job(workspace_id))
    executor = StubExecutor(_result())

    result = ResearchWorker(store, executor).run_once(workspace_id, job.id)

    assert result.status == "SUCCEEDED"
    assert executor.calls == 1
    assert store.get(workspace_id, job.id).status == ResearchJobStatus.SUCCEEDED


def test_worker_marks_job_failed_when_executor_raises():
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(_job(workspace_id))
    executor = StubExecutor(error=RuntimeError("scientific failure"))

    with pytest.raises(RuntimeError, match="scientific failure"):
        ResearchWorker(store, executor).run_once(workspace_id, job.id)

    assert store.get(workspace_id, job.id).status == ResearchJobStatus.FAILED


def test_worker_cannot_run_job_from_another_workspace():
    store = InMemoryResearchJobStore()
    owner = uuid4()
    other = uuid4()
    job = store.create(_job(owner))

    with pytest.raises(KeyError):
        ResearchWorker(store, StubExecutor(_result())).run_once(other, job.id)


def test_worker_cannot_double_claim_active_job():
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(_job(workspace_id))
    first = store.claim(workspace_id, job.id, "worker-a", 900)

    with pytest.raises(RuntimeError, match="already claimed"):
        store.claim(workspace_id, job.id, "worker-b", 900)

    store.finish(
        workspace_id,
        job.id,
        first.token,
        ResearchJobStatus.SUCCEEDED,
    )


def test_stale_lease_token_cannot_finish_job():
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(_job(workspace_id))
    store.claim(workspace_id, job.id, "worker-a", 900)

    with pytest.raises(RuntimeError, match="stale or invalid worker lease"):
        store.finish(
            workspace_id,
            job.id,
            uuid4(),
            ResearchJobStatus.SUCCEEDED,
        )


def test_expired_worker_lease_can_be_reclaimed():
    from datetime import datetime, timedelta, timezone

    now = [datetime(2026, 9, 18, tzinfo=timezone.utc)]
    store = InMemoryResearchJobStore(clock=lambda: now[0])
    workspace_id = uuid4()
    job = store.create(_job(workspace_id))
    first = store.claim(workspace_id, job.id, "worker-a", 10)

    now[0] += timedelta(seconds=11)
    second = store.claim(workspace_id, job.id, "worker-b", 10)

    assert second.token != first.token
    with pytest.raises(RuntimeError, match="stale or invalid worker lease"):
        store.finish(workspace_id, job.id, first.token, ResearchJobStatus.SUCCEEDED)
    store.finish(workspace_id, job.id, second.token, ResearchJobStatus.SUCCEEDED)
