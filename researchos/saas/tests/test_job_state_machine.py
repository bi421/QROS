from uuid import uuid4

import pytest

from researchos.saas.contracts import ResearchJob, ResearchJobStatus, is_valid_job_transition
from researchos.saas.store import InMemoryResearchJobStore


def _job(status: ResearchJobStatus = ResearchJobStatus.QUEUED) -> ResearchJob:
    return ResearchJob(
        id=uuid4(),
        workspace_id=uuid4(),
        dataset_id="dataset",
        workflow_id="workflow",
        status=status,
    )


def test_terminal_states_have_no_outgoing_transitions() -> None:
    assert not is_valid_job_transition(
        ResearchJobStatus.SUCCEEDED, ResearchJobStatus.RUNNING
    )
    assert not is_valid_job_transition(
        ResearchJobStatus.CANCELLED, ResearchJobStatus.QUEUED
    )


def test_failed_job_can_be_explicitly_requeued() -> None:
    assert is_valid_job_transition(ResearchJobStatus.FAILED, ResearchJobStatus.QUEUED)


def test_store_rejects_illegal_transition() -> None:
    store = InMemoryResearchJobStore()
    job = store.create(_job())

    with pytest.raises(ValueError, match="illegal job transition"):
        store.transition(
            job.workspace_id,
            job.id,
            ResearchJobStatus.QUEUED,
            ResearchJobStatus.SUCCEEDED,
        )


def test_store_accepts_valid_transition() -> None:
    store = InMemoryResearchJobStore()
    job = store.create(_job())

    updated = store.transition(
        job.workspace_id,
        job.id,
        ResearchJobStatus.QUEUED,
        ResearchJobStatus.RUNNING,
    )

    assert updated.status == ResearchJobStatus.RUNNING
