from io import BytesIO
from uuid import uuid4

from researchos.saas.datasets import DatasetVersion, InMemoryDatasetStore, storage_path_for, stream_sha256


def test_storage_path_is_tenant_content_version_addressed() -> None:
    tenant = uuid4()
    digest = "a" * 64
    assert storage_path_for(tenant, digest, 3) == f"tenant/{tenant}/datasets/{digest}/3/"


def test_same_content_is_deterministically_identified() -> None:
    store = InMemoryDatasetStore()
    tenant = uuid4()
    dataset = __import__("researchos.saas.datasets", fromlist=["Dataset"]).Dataset(
        id=uuid4(), workspace_id=tenant, name="x", created_by=uuid4()
    )
    store.create_dataset(tenant, dataset)
    digest, size = stream_sha256(BytesIO(b"same"), 1000)
    first = DatasetVersion(uuid4(), dataset.id, 1, digest, storage_path_for(tenant, digest, 1), size, uuid4())
    store.create_version(tenant, first)
    assert store.find_version_by_hash(tenant, dataset.id, digest) == first
    assert store.find_version_by_hash(tenant, dataset.id, "b" * 64) is None
