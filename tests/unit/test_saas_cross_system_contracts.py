from __future__ import annotations

from io import BytesIO
from uuid import uuid4

from researchos.saas.datasets import Dataset, InMemoryDatasetStorage, InMemoryDatasetStore
from researchos.saas.queue import InMemoryResearchJobQueue


def test_inmemory_dataset_store_honors_api_sort_contract() -> None:
    workspace_id = uuid4()
    store = InMemoryDatasetStore()
    first = Dataset(uuid4(), workspace_id, "Zulu", uuid4())
    second = Dataset(uuid4(), workspace_id, "Alpha", uuid4())
    store.create_dataset(workspace_id, first)
    store.create_dataset(workspace_id, second)

    rows, total = store.list_datasets(
        workspace_id,
        sort_by="name",
        sort_order="asc",
    )

    assert total == 2
    assert [row.name for row in rows] == ["Alpha", "Zulu"]


def test_supplied_dataset_storage_contract_verifies_content_hash() -> None:
    storage = InMemoryDatasetStorage()
    path = "tenant/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/datasets/hash/1/"
    payload = b"qros"
    storage.put(path, BytesIO(payload))

    import hashlib

    assert storage.download_verified(path, hashlib.sha256(payload).hexdigest()) == payload


def test_inmemory_queue_initializes_request_id_contract() -> None:
    queue = InMemoryResearchJobQueue()
    workspace_id = uuid4()
    job_id = uuid4()

    queue.enqueue(workspace_id, job_id, request_id="req-123")

    assert queue.request_ids[job_id] == "req-123"
