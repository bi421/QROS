from io import BytesIO
from uuid import uuid4

import pytest

from researchos.saas.datasets import (
    Dataset,
    DatasetVersion,
    InMemoryDatasetStorage,
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

    assert path == f"tenant/{workspace_id}/datasets/{digest}/1/"
    assert str(dataset_id) not in path


def test_in_memory_store_rejects_duplicate_version_identity() -> None:
    store = InMemoryDatasetStore()
    dataset = Dataset(uuid4(), uuid4(), "sample", uuid4())
    store.create_dataset(dataset.workspace_id, dataset)
    first = DatasetVersion(uuid4(), dataset.id, 1, "a" * 64, "path/a", 1, dataset.created_by)
    second = DatasetVersion(uuid4(), dataset.id, 2, "b" * 64, "path/b", 1, dataset.created_by)

    store.create_version(dataset.workspace_id, first)
    store.create_version(dataset.workspace_id, second)

    assert store.find_version_by_content(dataset.workspace_id, dataset.id, "a" * 64) == first
    assert store.list_versions(dataset.workspace_id, dataset.id) == [first, second]


def test_in_memory_store_rejects_version_write_from_other_workspace() -> None:
    owner_workspace = uuid4()
    other_workspace = uuid4()
    dataset = Dataset(uuid4(), owner_workspace, "sample", uuid4())
    store = InMemoryDatasetStore()
    store.create_dataset(dataset.workspace_id, dataset)

    version = DatasetVersion(
        uuid4(), dataset.id, 1, "b" * 64, "path/b", 1, dataset.created_by
    )

    with pytest.raises(KeyError, match="dataset not found for workspace"):
        store.create_version(other_workspace, version)


def test_in_memory_store_rejects_dataset_write_from_other_workspace() -> None:
    owner_workspace = uuid4()
    other_workspace = uuid4()
    dataset = Dataset(uuid4(), owner_workspace, "sample", uuid4())
    store = InMemoryDatasetStore()

    with pytest.raises(ValueError, match="dataset workspace does not match tenant"):
        store.create_dataset(other_workspace, dataset)

    assert store.get_dataset(owner_workspace, dataset.id) is None


def test_in_memory_signed_download_url_requires_existing_object_and_bounded_expiry() -> None:
    storage = InMemoryDatasetStorage()
    with pytest.raises(FileNotFoundError):
        storage.create_signed_download_url("missing", 3600)

    storage.put("tenant/object", BytesIO(b"data"))
    assert storage.create_signed_download_url("tenant/object", 3600).endswith("?expires_in=3600")

    for expires_in in (0, 3599, 3601):
        with pytest.raises(ValueError, match="signed URL expiry"):
            storage.create_signed_download_url("tenant/object", expires_in)


def test_same_content_is_deduplicated_to_the_existing_version_path() -> None:
    store = InMemoryDatasetStore()
    dataset = Dataset(uuid4(), uuid4(), "sample", uuid4())
    store.create_dataset(dataset.workspace_id, dataset)
    digest = "c" * 64
    first = DatasetVersion(uuid4(), dataset.id, 1, digest, storage_path_for(dataset.workspace_id, digest, 1), 3, dataset.created_by)
    store.create_version(dataset.workspace_id, first)

    assert store.find_version_by_content(dataset.workspace_id, dataset.id, digest) is first
    assert storage_path_for(dataset.workspace_id, digest, 1) == first.storage_path


def test_old_versions_remain_readable_after_new_version() -> None:
    store = InMemoryDatasetStore()
    dataset = Dataset(uuid4(), uuid4(), "sample", uuid4())
    store.create_dataset(dataset.workspace_id, dataset)
    first = DatasetVersion(uuid4(), dataset.id, 1, "d" * 64, storage_path_for(dataset.workspace_id, "d" * 64, 1), 1, dataset.created_by)
    second = DatasetVersion(uuid4(), dataset.id, 2, "e" * 64, storage_path_for(dataset.workspace_id, "e" * 64, 2), 1, dataset.created_by)
    store.create_version(dataset.workspace_id, first)
    store.create_version(dataset.workspace_id, second)

    assert store.get_version(dataset.workspace_id, first.id) == first
    assert store.get_version(dataset.workspace_id, second.id) == second


def test_storage_path_rejects_noncanonical_digest() -> None:
    workspace_id = uuid4()

    with pytest.raises(ValueError, match="SHA-256 digest"):
        storage_path_for(workspace_id, "A" * 64, 1)

    with pytest.raises(ValueError, match="SHA-256 digest"):
        storage_path_for(workspace_id, "not-a-digest", 1)


def test_version_storage_path_is_immutable_and_canonical() -> None:
    store = InMemoryDatasetStore()
    dataset = Dataset(uuid4(), uuid4(), "sample", uuid4())
    store.create_dataset(dataset.workspace_id, dataset)
    digest = "f" * 64

    valid = DatasetVersion(
        uuid4(), dataset.id, 1, digest,
        storage_path_for(dataset.workspace_id, digest, 1),
        1, dataset.created_by,
    )
    store.create_version(dataset.workspace_id, valid)

    invalid = DatasetVersion(
        uuid4(), dataset.id, 2, digest,
        "tenant/other/datasets/" + digest + "/2/",
        1, dataset.created_by,
    )
    with pytest.raises(ValueError, match="canonical content-addressed path"):
        store.create_version(dataset.workspace_id, invalid)


def test_storage_sha256_verification_detects_tampering() -> None:
    storage = InMemoryDatasetStorage()
    path = "tenant/example/datasets/" + "a" * 64 + "/1/"
    storage.put(path, BytesIO(b"original"))

    assert storage.verify_sha256(path, "0" * 64) is False


def test_tenant_b_cannot_generate_signed_url_for_tenant_a_file() -> None:
    storage = InMemoryDatasetStorage()
    tenant_a = uuid4()
    tenant_b = uuid4()
    digest = "a" * 64
    path = storage_path_for(tenant_a, digest, 1)
    storage.put(path, BytesIO(b"tenant-a"), tenant_id=tenant_a)

    with pytest.raises(PermissionError, match="outside tenant context"):
        storage.create_signed_download_url(
            path,
            3600,
            tenant_id=tenant_b,
            access_token="tenant-b-token",
        )

    assert storage.create_signed_download_url(
        path,
        3600,
        tenant_id=tenant_a,
        access_token="tenant-a-token",
    ).startswith(f"memory://tenant/{tenant_a}/datasets/{digest}/1/")


def test_direct_storage_path_without_tenant_prefix_is_rejected() -> None:
    storage = InMemoryDatasetStorage()
    tenant = uuid4()

    with pytest.raises(PermissionError, match="outside tenant context"):
        storage.put("datasets/" + "a" * 64 + "/1/", BytesIO(b"bad"), tenant_id=tenant)
