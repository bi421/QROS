from datetime import datetime, timedelta, timezone
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


def _job(workspace_id, *, max_attempts=3):
    return ResearchJob(
        id=uuid4(),
        workspace_id=workspace_id,
        dataset_version_id=uuid4(),
        workflow_id="xauusd_m1_frozen_research_v1",
        status=ResearchJobStatus.QUEUED,
        source_dataset_sha256="0" * 64,
        max_attempts=max_attempts,
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
    saved = store.get(workspace_id, job.id)
    assert saved.status == ResearchJobStatus.SUCCEEDED
    assert saved.attempt_count == 1


def test_worker_marks_job_failed_when_executor_raises():
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(_job(workspace_id))
    executor = StubExecutor(error=RuntimeError("scientific failure"))

    with pytest.raises(RuntimeError, match="scientific failure"):
        ResearchWorker(store, executor).run_once(workspace_id, job.id)

    saved = store.get(workspace_id, job.id)
    assert saved.status == ResearchJobStatus.FAILED
    assert saved.error_code == "executor_error"
    assert saved.attempt_count == 1


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

    store.finish(workspace_id, job.id, first.token, ResearchJobStatus.SUCCEEDED)


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


def test_expired_worker_lease_can_be_reclaimed_until_attempt_budget_is_exhausted():
    now = [datetime(2026, 9, 18, tzinfo=timezone.utc)]
    store = InMemoryResearchJobStore(clock=lambda: now[0])
    workspace_id = uuid4()
    job = store.create(_job(workspace_id, max_attempts=2))

    first = store.claim(workspace_id, job.id, "worker-a", 10)
    assert first.job.attempt_count == 1

    now[0] += timedelta(seconds=11)
    second = store.claim(workspace_id, job.id, "worker-b", 10)
    assert second.token != first.token
    assert second.job.attempt_count == 2

    now[0] += timedelta(seconds=11)
    with pytest.raises(RuntimeError, match="exhausted retry attempts"):
        store.claim(workspace_id, job.id, "worker-c", 10)

    saved = store.get(workspace_id, job.id)
    assert saved.status == ResearchJobStatus.FAILED
    assert saved.error_code == "max_attempts_exceeded"
    assert saved.attempt_count == 2

    with pytest.raises(RuntimeError, match="already claimed"):
        store.claim(workspace_id, job.id, "worker-d", 10)


def test_stale_lease_token_cannot_finish_after_reclaim():
    now = [datetime(2026, 9, 18, tzinfo=timezone.utc)]
    store = InMemoryResearchJobStore(clock=lambda: now[0])
    workspace_id = uuid4()
    job = store.create(_job(workspace_id, max_attempts=2))
    first = store.claim(workspace_id, job.id, "worker-a", 10)

    now[0] += timedelta(seconds=11)
    second = store.claim(workspace_id, job.id, "worker-b", 10)

    with pytest.raises(RuntimeError, match="stale or invalid worker lease"):
        store.finish(workspace_id, job.id, first.token, ResearchJobStatus.SUCCEEDED)
    store.finish(workspace_id, job.id, second.token, ResearchJobStatus.SUCCEEDED)


def test_worker_lease_can_be_renewed_before_expiry():
    now = [datetime(2026, 9, 18, tzinfo=timezone.utc)]
    store = InMemoryResearchJobStore(clock=lambda: now[0])
    workspace_id = uuid4()
    job = store.create(_job(workspace_id))
    lease = store.claim(workspace_id, job.id, "worker-a", 10)

    now[0] += timedelta(seconds=5)
    renewed = store.renew(workspace_id, job.id, lease.token, 10)

    assert renewed.token == lease.token
    now[0] += timedelta(seconds=6)
    store.finish(workspace_id, job.id, lease.token, ResearchJobStatus.SUCCEEDED)


def test_worker_persists_provenance_before_succeeding():
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(_job(workspace_id))
    result = ResearchWorker(store, StubExecutor(_result())).run_once(workspace_id, job.id)

    saved_result = store.get_result(workspace_id, job.id)
    assert saved_result is not None
    assert saved_result.source_dataset_sha256 == result.source_dataset_sha256
    assert saved_result.manifest_sha256
    assert saved_result.artifacts == result.artifacts


def test_worker_rejects_result_from_different_source_dataset():
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(_job(workspace_id))
    mismatched = ResearchResult(
        status="SUCCEEDED",
        source_dataset_sha256="f" * 64,
        artifacts=(ResearchArtifact("artifact-1", "evidence", "1" * 64),),
    )

    with pytest.raises(ValueError, match="source hash does not match"):
        ResearchWorker(store, StubExecutor(mismatched)).run_once(workspace_id, job.id)

    saved = store.get(workspace_id, job.id)
    assert saved.status == ResearchJobStatus.FAILED
    assert saved.error_code == "provenance_error"
    assert store.get_result(workspace_id, job.id) is None
