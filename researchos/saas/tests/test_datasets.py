from io import BytesIO
from uuid import uuid4

import pytest

from researchos.saas.datasets import (
    Dataset,
    DatasetVersion,
    InMemoryDatasetStore,
    storage_path_for,
    stream_sha256,
)


def test_stream_sha256_returns_digest_size_and_rewinds_file() -> None:
    body = b"xauusd,test\n1,100\n"
    file = BytesIO(body)

    digest, size = stream_sha256(file, max_bytes=1024)

    assert size == len(body)
    assert digest == "2c4205ccf87a7d1e36e14624540e63088c7b33c1a05f7e3ac02b7505fa042dcd"
    assert file.read() == body


def test_stream_sha256_rejects_over_limit() -> None:
    with pytest.raises(ValueError, match="dataset exceeds plan upload limit"):
        stream_sha256(BytesIO(b"12345"), max_bytes=4)


def test_storage_path_is_tenant_scoped_and_content_addressed() -> None:
    workspace_id = uuid4()
    dataset_id = uuid4()
    digest = "a" * 64

    path = storage_path_for(workspace_id, dataset_id, digest)

    assert path == f"{workspace_id}/datasets/{dataset_id}/sha256/{digest}"
    assert "versions" not in path


def test_in_memory_store_rejects_duplicate_content() -> None:
    store = InMemoryDatasetStore()
    dataset = Dataset(uuid4(), uuid4(), "sample", uuid4())
    store.create_dataset(dataset)
    first = DatasetVersion(uuid4(), dataset.id, 1, "a" * 64, "path/a", 1, dataset.created_by)
    second = DatasetVersion(uuid4(), dataset.id, 2, "a" * 64, "path/b", 1, dataset.created_by)

    store.create_version(dataset.workspace_id, first)

    with pytest.raises(ValueError, match="dataset content already exists"):
        store.create_version(dataset.workspace_id, second)


def test_in_memory_store_rejects_version_write_from_other_workspace() -> None:
    owner_workspace = uuid4()
    other_workspace = uuid4()
    dataset = Dataset(uuid4(), owner_workspace, "sample", uuid4())
    store = InMemoryDatasetStore()
    store.create_dataset(dataset)

    version = DatasetVersion(
        uuid4(), dataset.id, 1, "b" * 64, "path/b", 1, dataset.created_by
    )

    with pytest.raises(KeyError, match="dataset not found for workspace"):
        store.create_version(other_workspace, version)
