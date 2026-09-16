from uuid import uuid4

import pytest

from researchos.research_core.contracts import ResearchArtifact, ResearchResult
from researchos.saas.contracts import ResearchJob, ResearchJobStatus
from researchos.saas.store import InMemoryResearchJobStore
from researchos.saas.worker import ResearchWorker


class StubExecutor:
    def __init__(self, result: ResearchResult | None = None, error: Exception | None = None) -> None:
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
    return ResearchResult(
        status=status,
        source_dataset_sha256="0" * 64,
        artifacts=(
            ResearchArtifact("artifact-1", "evidence", "1" * 64),
        ) if status == "SUCCEEDED" else (),
    )


def test_worker_moves_queued_job_to_succeeded() -> None:
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(_job(workspace_id))
    executor = StubExecutor(_result())

    result = ResearchWorker(store, executor).run_once(workspace_id, job.id)

    assert result.status == "SUCCEEDED"
    assert executor.calls == 1
    assert store.get(workspace_id, job.id).status == ResearchJobStatus.SUCCEEDED


def test_worker_marks_job_failed_when_executor_raises() -> None:
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = store.create(_job(workspace_id))
    executor = StubExecutor(error=RuntimeError("scientific failure"))

    with pytest.raises(RuntimeError, match="scientific failure"):
        ResearchWorker(store, executor).run_once(workspace_id, job.id)

    assert store.get(workspace_id, job.id).status == ResearchJobStatus.FAILED


def test_worker_cannot_run_job_from_another_workspace() -> None:
    store = InMemoryResearchJobStore()
    owner = uuid4()
    other = uuid4()
    job = store.create(_job(owner))

    with pytest.raises(KeyError):
        ResearchWorker(store, StubExecutor(_result())).run_once(other, job.id)
