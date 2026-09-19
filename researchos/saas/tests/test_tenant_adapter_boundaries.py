from __future__ import annotations

from uuid import uuid4

import pytest

from researchos.claims.claim import ResearchClaim
from researchos.saas.datasets import Dataset, DatasetVersion, SupabaseDatasetStore, storage_path_for
from researchos.saas.supabase_claim_store import SupabaseResearchClaimStore


class _Response:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.rows = []
        self.result_rows = []
        self.filters = {}

    def insert(self, row):
        self.client.writes.append(("insert", self.table, row))
        return self

    def upsert(self, row, **kwargs):
        self.client.writes.append(("upsert", self.table, row))
        return self

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, *_args):
        return self

    def order(self, *_args):
        return self

    def range(self, *_args):
        return self

    def execute(self):
        return _Response(self.client.responses.get(self.table, self.result_rows))


class _Client:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.writes = []
        self.tables = []

    def table(self, name):
        self.tables.append(name)
        return _Query(self, name)


def test_supabase_dataset_create_rejects_cross_tenant_object_before_write():
    tenant = uuid4()
    foreign = uuid4()
    client = _Client()
    store = SupabaseDatasetStore(client)
    dataset = Dataset(uuid4(), foreign, "foreign", uuid4())

    with pytest.raises(ValueError, match="workspace does not match tenant"):
        store.create_dataset(tenant, dataset)

    assert client.writes == []


def test_supabase_dataset_version_rejects_foreign_parent_without_version_insert():
    tenant = uuid4()
    foreign_dataset = uuid4()
    version = DatasetVersion(
        id=uuid4(),
        dataset_id=foreign_dataset,
        version_no=1,
        content_sha256="a" * 64,
        storage_path=f"{foreign_dataset}/sha256/" + "a" * 64,
        byte_size=1,
        created_by=uuid4(),
    )
    client = _Client(responses={"dataset": []})
    store = SupabaseDatasetStore(client)

    with pytest.raises(KeyError, match="dataset not found for workspace"):
        store.create_version(tenant, version)

    assert not any(
        kind == "insert" and table == "dataset_version"
        for kind, table, _ in client.writes
    )


def test_supabase_claim_save_rejects_cross_tenant_object_before_write():
    tenant = uuid4()
    foreign = uuid4()
    client = _Client()
    store = SupabaseResearchClaimStore(client)
    claim = ResearchClaim(
        statement="foreign claim",
        creator=str(uuid4()),
        workspace_id=str(foreign),
        research_id="research-1",
    )

    with pytest.raises(ValueError, match="workspace does not match tenant"):
        store.save(tenant, claim)

    assert client.writes == []


def test_supabase_dataset_version_accepts_matching_parent_and_writes():
    tenant = uuid4()
    dataset = Dataset(uuid4(), tenant, "dataset", uuid4())
    version = DatasetVersion(
        id=uuid4(),
        dataset_id=dataset.id,
        version_no=1,
        content_sha256="b" * 64,
        storage_path=f"{tenant}/datasets/{dataset.id}/sha256/" + "b" * 64,
        byte_size=1,
        created_by=uuid4(),
    )
    client = _Client(
        responses={
            "dataset": [{
                "id": str(dataset.id),
                "workspace_id": str(tenant),
                "name": dataset.name,
                "created_by": str(dataset.created_by),
            }],
            "dataset_version": [{
                "id": str(version.id),
                "dataset_id": str(version.dataset_id),
                "version_no": version.version_no,
                "content_sha256": version.content_sha256,
                "storage_path": version.storage_path,
                "byte_size": version.byte_size,
                "created_by": str(version.created_by),
            }],
        }
    )
    store = SupabaseDatasetStore(client)

    created = store.create_version(tenant, version)

    assert created == version
    assert any(
        kind == "insert" and table == "dataset_version"
        for kind, table, _ in client.writes
    )


def test_storage_path_is_tenant_scoped_and_content_addressed():
    tenant = uuid4()
    dataset = uuid4()
    digest = "c" * 64

    path = storage_path_for(tenant, dataset, digest)

    assert path == f"{tenant}/datasets/{dataset}/sha256/{digest}"
    assert str(uuid4()) not in path
    assert path.startswith(f"{tenant}/")
