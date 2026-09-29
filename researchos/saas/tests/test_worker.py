from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from researchos.research_core.contracts import ResearchArtifact, ResearchResult
from researchos.saas.contracts import ResearchJob, ResearchJobStatus
from researchos.saas.observability import job_id_var, tenant_id_var
from researchos.saas.store import InMemoryResearchJobStore
from researchos.saas.worker import ResearchWorker


class StubExecutor:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0
        self.observed_job_id = None
        self.observed_tenant_id = None

    def execute(self, job_id):
        self.observed_job_id = job_id_var.get()
        self.observed_tenant_id = tenant_id_var.get()
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


def test_worker_moves_queued_job_to_succeeded(monkeypatch):
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(workspace_id, _job(workspace_id))
    executor = StubExecutor(_result())
    durations = []
    monkeypatch.setattr(
        "researchos.saas.worker.jobs_duration_seconds.observe",
        durations.append,
    )

    result = ResearchWorker(store, executor).run_once(workspace_id, job.id)

    assert result.status == "SUCCEEDED"
    assert executor.calls == 1
    assert executor.observed_job_id == str(job.id)
    assert executor.observed_tenant_id == str(workspace_id)
    assert len(durations) == 1
    assert durations[0] >= 0.0
    assert job_id_var.get() is None
    assert tenant_id_var.get() is None
    saved = store.get(workspace_id, job.id)
    assert saved.status == ResearchJobStatus.SUCCEEDED
    assert saved.attempt_count == 1


def test_worker_marks_job_failed_when_executor_raises(monkeypatch):
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(workspace_id, _job(workspace_id))
    executor = StubExecutor(error=RuntimeError("scientific failure"))
    failures = []
    durations = []
    monkeypatch.setattr(
        "researchos.saas.worker.jobs_failed_total.inc",
        lambda: failures.append(True),
    )
    monkeypatch.setattr(
        "researchos.saas.worker.jobs_duration_seconds.observe",
        durations.append,
    )

    with pytest.raises(RuntimeError, match="scientific failure"):
        ResearchWorker(store, executor).run_once(workspace_id, job.id)

    assert len(failures) == 1
    assert len(durations) == 1
    assert durations[0] >= 0.0
    assert job_id_var.get() is None
    assert tenant_id_var.get() is None
    saved = store.get(workspace_id, job.id)
    assert saved.status == ResearchJobStatus.FAILED
    assert saved.error_code == "executor_error"
    assert saved.attempt_count == 1


def test_worker_records_terminal_failed_result(monkeypatch):
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(workspace_id, _job(workspace_id))
    executor = StubExecutor(_result("FAILED"))
    failures = []
    monkeypatch.setattr(
        "researchos.saas.worker.jobs_failed_total.inc",
        lambda: failures.append(True),
    )

    result = ResearchWorker(store, executor).run_once(workspace_id, job.id)

    assert result.status == "FAILED"
    assert failures == [True]
    saved = store.get(workspace_id, job.id)
    assert saved.status == ResearchJobStatus.FAILED


def test_worker_marks_job_failed_when_provenance_recording_fails(monkeypatch):
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(workspace_id, _job(workspace_id))
    executor = StubExecutor(_result())
    failures = []
    monkeypatch.setattr(
        "researchos.saas.worker.jobs_failed_total.inc",
        lambda: failures.append(True),
    )

    def fail_record(*args, **kwargs):
        raise RuntimeError("persistence failure")

    monkeypatch.setattr(store, "record_result", fail_record)

    with pytest.raises(RuntimeError, match="persistence failure"):
        ResearchWorker(store, executor).run_once(workspace_id, job.id)

    assert len(failures) == 1
    assert job_id_var.get() is None
    assert tenant_id_var.get() is None


def test_worker_cannot_run_job_from_another_workspace():
    store = InMemoryResearchJobStore()
    owner = uuid4()
    other = uuid4()
    job = store.create(owner, _job(owner))

    with pytest.raises(KeyError):
        ResearchWorker(store, StubExecutor(_result())).run_once(other, job.id)


def test_worker_cannot_double_claim_active_job():
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(workspace_id, _job(workspace_id))
    first = store.claim(workspace_id, job.id, "worker-a", 900)

    with pytest.raises(RuntimeError, match="already claimed"):
        store.claim(workspace_id, job.id, "worker-b", 900)

    store.finish(workspace_id, job.id, first.token, ResearchJobStatus.SUCCEEDED)


def test_stale_lease_token_cannot_finish_job():
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(workspace_id, _job(workspace_id))
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
    job = store.create(workspace_id, _job(workspace_id, max_attempts=2))

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
    job = store.create(workspace_id, _job(workspace_id, max_attempts=2))

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
    job = store.create(workspace_id, _job(workspace_id))
    lease = store.claim(workspace_id, job.id, "worker-a", 10)

    now[0] += timedelta(seconds=5)
    renewed = store.renew(workspace_id, job.id, lease.token, 10)

    assert renewed.token == lease.token
    now[0] += timedelta(seconds=6)
    store.finish(workspace_id, job.id, lease.token, ResearchJobStatus.SUCCEEDED)


def test_worker_persists_provenance_before_succeeding():
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(workspace_id, _job(workspace_id))
    result = ResearchWorker(store, StubExecutor(_result())).run_once(workspace_id, job.id)

    saved_result = store.get_result(workspace_id, job.id)
    assert saved_result is not None
    assert saved_result.source_dataset_sha256 == result.source_dataset_sha256
    assert saved_result.manifest_sha256
    assert saved_result.artifacts == result.artifacts


def test_worker_rejects_result_from_different_source_dataset():
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(workspace_id, _job(workspace_id))
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


def test_direct_job_write_rejects_mismatched_workspace():
    store = InMemoryResearchJobStore()
    owner = uuid4()
    other = uuid4()
    with pytest.raises(ValueError, match="workspace does not match tenant"):
        store.create(other, _job(owner))


def test_recovered_worker_reuses_idempotent_result_after_lease_loss():
    now = [datetime(2026, 9, 21, tzinfo=timezone.utc)]
    store = InMemoryResearchJobStore(clock=lambda: now[0])
    workspace_id = uuid4()
    job = store.create(workspace_id, _job(workspace_id, max_attempts=3))
    result = _result()

    first = store.claim(workspace_id, job.id, "worker-a", 10)
    first_record = store.record_result(workspace_id, job.id, first.token, result)

    now[0] += timedelta(seconds=11)
    second = store.claim(workspace_id, job.id, "worker-b", 10)
    recovered_record = store.record_result(workspace_id, job.id, second.token, result)
    store.finish(workspace_id, job.id, second.token, ResearchJobStatus.SUCCEEDED)

    assert recovered_record.manifest_sha256 == first_record.manifest_sha256
    assert store.get_result(workspace_id, job.id) == first_record
    assert store.get(workspace_id, job.id).status == ResearchJobStatus.SUCCEEDED
    assert store.get(workspace_id, job.id).attempt_count == 2

 
def test_in_memory_monthly_usage_rolls_over_at_month_boundary() -> None:
    now = [datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc)]
    store = InMemoryResearchJobStore(clock=lambda: now[0])
    workspace_id = uuid4()

    store.create(workspace_id, _job(workspace_id))
    assert store.count_monthly(workspace_id) == 1

    now[0] = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    assert store.count_monthly(workspace_id) == 0
