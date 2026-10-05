from uuid import uuid4

import pytest

from researchos.research_core.contracts import ResearchArtifact, ResearchResult
from researchos.saas.contracts import ResearchJob, ResearchJobStatus
from researchos.saas.datasets import (
    Dataset,
    DatasetVersion,
    storage_path_for,
    InMemoryDatasetStorage,
    InMemoryDatasetStore,
)
from researchos.saas.queue import InMemoryResearchJobQueue, ResearchQueueMessage
from researchos.saas.research_executor import GovernedResearchExecutor
from researchos.saas.store import InMemoryResearchJobStore


def _job(workspace_id, dataset_version_id, source_sha, workflow="xauusd_m1_frozen_research_v1"):
    return ResearchJob(
        id=uuid4(),
        workspace_id=workspace_id,
        dataset_version_id=dataset_version_id,
        workflow_id=workflow,
        status=ResearchJobStatus.QUEUED,
        source_dataset_sha256=source_sha,
    )


def test_governed_executor_fails_closed_on_missing_version():
    workspace_id = uuid4()
    store = InMemoryResearchJobStore()
    job = _job(workspace_id, uuid4(), "0" * 64)
    store.create(workspace_id, job)

    executor = GovernedResearchExecutor(
        store,
        InMemoryDatasetStore(),
        InMemoryDatasetStorage(),
        workspace_id,
    )

    with pytest.raises(KeyError, match="dataset version"):
        executor.execute(job.id)


def test_governed_executor_rejects_cross_tenant_dataset_version():
    owner = uuid4()
    other = uuid4()
    dataset_store = InMemoryDatasetStore()
    dataset = Dataset(uuid4(), owner, "xauusd", uuid4())
    dataset_store.create_dataset(owner, dataset)
    version = DatasetVersion(
        uuid4(), dataset.id, 1, "0" * 64, storage_path_for(owner, "0" * 64, 1), 1, dataset.created_by
    )
    dataset_store.create_version(owner, version)
    store = InMemoryResearchJobStore()
    job = _job(other, version.id, version.content_sha256)
    store.create(other, job)

    executor = GovernedResearchExecutor(
        store,
        dataset_store,
        InMemoryDatasetStorage(),
        other,
    )

    with pytest.raises(KeyError, match="dataset version"):
        executor.execute(job.id)


def test_executor_result_source_sha_contract_is_preserved():
    result = ResearchResult(
        status="SUCCEEDED",
        source_dataset_sha256="0" * 64,
        artifacts=(ResearchArtifact("a", "evidence", "1" * 64),),
    )
    assert result.source_dataset_sha256 == "0" * 64


def test_in_memory_queue_message_lifecycle_is_identifier_only():
    workspace_id = uuid4()
    job_id = uuid4()
    queue = InMemoryResearchJobQueue()
    message_id = queue.enqueue(workspace_id, job_id)

    assert queue.receive() == ResearchQueueMessage(message_id, workspace_id, job_id)
    queue.ack(message_id)
    assert queue.messages == []
