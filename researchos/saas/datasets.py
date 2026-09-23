"""Tenant-scoped dataset persistence and storage boundaries.

The store separates dataset identity from immutable version identity. Production
authorization remains tenant-scoped in the persistence layer (Supabase/RLS).
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import BinaryIO, Protocol
from uuid import UUID


@dataclass(frozen=True)
class Dataset:
    id: UUID
    workspace_id: UUID
    name: str
    created_by: UUID


@dataclass(frozen=True)
class DatasetVersion:
    id: UUID
    dataset_id: UUID
    version_no: int
    content_sha256: str
    storage_path: str
    byte_size: int
    created_by: UUID


class DatasetStore(Protocol):
    def create_dataset(self, workspace_id: UUID, dataset: Dataset) -> Dataset:
        """Create a dataset only when its tenant identity matches the boundary."""
        ...

    def delete_dataset(self, workspace_id: UUID, dataset_id: UUID) -> None:
        ...

    def create_version(self, workspace_id: UUID, version: DatasetVersion) -> DatasetVersion:
        ...

    def get_dataset(self, workspace_id: UUID, dataset_id: UUID) -> Dataset | None:
        ...

    def get_version(self, workspace_id: UUID, version_id: UUID) -> DatasetVersion | None:
        ...

    def list_versions(self, workspace_id: UUID, dataset_id: UUID) -> list[DatasetVersion]:
        ...


class DatasetStorage(Protocol):
    def put(self, storage_path: str, file: BinaryIO) -> None:
        ...

    def remove(self, storage_path: str) -> None:
        ...


class InMemoryDatasetStore:
    """Deterministic development/test implementation; not production storage."""

    def __init__(self) -> None:
        self._datasets: dict[UUID, Dataset] = {}
        self._versions: dict[UUID, DatasetVersion] = {}

    def create_dataset(self, workspace_id: UUID, dataset: Dataset) -> Dataset:
        if dataset.workspace_id != workspace_id:
            raise ValueError("dataset workspace does not match tenant")
        if dataset.id in self._datasets:
            raise ValueError("dataset already exists")
        self._datasets[dataset.id] = dataset
        return dataset

    def delete_dataset(self, workspace_id: UUID, dataset_id: UUID) -> None:
        dataset = self.get_dataset(workspace_id, dataset_id)
        if dataset is None:
            return
        if any(v.dataset_id == dataset_id for v in self._versions.values()):
            raise ValueError("cannot delete dataset with versions")
        del self._datasets[dataset_id]

    def create_version(self, workspace_id: UUID, version: DatasetVersion) -> DatasetVersion:
        if version.id in self._versions:
            raise ValueError("dataset version already exists")
        if self.get_dataset(workspace_id, version.dataset_id) is None:
            raise KeyError("dataset not found for workspace")
        existing = [v for v in self._versions.values() if v.dataset_id == version.dataset_id]
        if any(v.version_no == version.version_no for v in existing):
            raise ValueError("dataset version number already exists")
        if any(v.content_sha256 == version.content_sha256 for v in existing):
            raise ValueError("dataset content already exists")
        self._versions[version.id] = version
        return version

    def get_dataset(self, workspace_id: UUID, dataset_id: UUID) -> Dataset | None:
        dataset = self._datasets.get(dataset_id)
        if dataset is None or dataset.workspace_id != workspace_id:
            return None
        return dataset

    def get_version(self, workspace_id: UUID, version_id: UUID) -> DatasetVersion | None:
        version = self._versions.get(version_id)
        if version is None:
            return None
        return version if self.get_dataset(workspace_id, version.dataset_id) is not None else None

    def list_versions(self, workspace_id: UUID, dataset_id: UUID) -> list[DatasetVersion]:
        if self.get_dataset(workspace_id, dataset_id) is None:
            return []
        return sorted(
            (v for v in self._versions.values() if v.dataset_id == dataset_id),
            key=lambda v: v.version_no,
        )


class InMemoryDatasetStorage:
    """Byte-backed test storage with deterministic object replacement protection."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def put(self, storage_path: str, file: BinaryIO) -> None:
        if storage_path in self._objects:
            raise ValueError("storage object already exists")
        self._objects[storage_path] = file.read()

    def remove(self, storage_path: str) -> None:
        self._objects.pop(storage_path, None)

    def get(self, storage_path: str) -> bytes | None:
        return self._objects.get(storage_path)


class SupabaseDatasetStore:
    """Supabase/Postgres adapter; RLS remains the tenant authorization boundary."""

    def __init__(self, supabase_client: object) -> None:
        self._client = supabase_client

    @staticmethod
    def _dataset(row: dict[str, object]) -> Dataset:
        return Dataset(
            id=UUID(str(row["id"])),
            workspace_id=UUID(str(row["workspace_id"])),
            name=str(row["name"]),
            created_by=UUID(str(row["created_by"])),
        )

    @staticmethod
    def _version(row: dict[str, object]) -> DatasetVersion:
        return DatasetVersion(
            id=UUID(str(row["id"])),
            dataset_id=UUID(str(row["dataset_id"])),
            version_no=int(row["version_no"]),
            content_sha256=str(row["content_sha256"]),
            storage_path=str(row["storage_path"]),
            byte_size=int(row["byte_size"]),
            created_by=UUID(str(row["created_by"])),
        )

    def create_dataset(self, workspace_id: UUID, dataset: Dataset) -> Dataset:
        if dataset.workspace_id != workspace_id:
            raise ValueError("dataset workspace does not match tenant")
        result = (
            self._client.table("dataset")
            .insert(
                {
                    "id": str(dataset.id),
                    "workspace_id": str(dataset.workspace_id),
                    "name": dataset.name,
                    "created_by": str(dataset.created_by),
                }
            )
            .select("id,workspace_id,name,created_by")
            .execute()
        )
        rows = result.data or []
        if len(rows) != 1:
            raise RuntimeError("dataset insert returned no unique row")
        return self._dataset(rows[0])

    def delete_dataset(self, workspace_id: UUID, dataset_id: UUID) -> None:
        self._client.table("dataset").delete().eq("id", str(dataset_id)).eq(
            "workspace_id", str(workspace_id)
        ).execute()

    def create_version(self, workspace_id: UUID, version: DatasetVersion) -> DatasetVersion:
        if self.get_dataset(workspace_id, version.dataset_id) is None:
            raise KeyError("dataset not found for workspace")
        result = (
            self._client.table("dataset_version")
            .insert(
                {
                    "id": str(version.id),
                    "dataset_id": str(version.dataset_id),
                    "version_no": version.version_no,
                    "content_sha256": version.content_sha256,
                    "storage_path": version.storage_path,
                    "byte_size": version.byte_size,
                    "created_by": str(version.created_by),
                }
            )
            .select("id,dataset_id,version_no,content_sha256,storage_path,byte_size,created_by")
            .execute()
        )
        rows = result.data or []
        if len(rows) != 1:
            raise RuntimeError("dataset version insert returned no unique row")
        return self._version(rows[0])

    def get_dataset(self, workspace_id: UUID, dataset_id: UUID) -> Dataset | None:
        result = (
            self._client.table("dataset")
            .select("id,workspace_id,name,created_by")
            .eq("id", str(dataset_id))
            .eq("workspace_id", str(workspace_id))
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return self._dataset(rows[0]) if rows else None

    def get_version(self, workspace_id: UUID, version_id: UUID) -> DatasetVersion | None:
        result = (
            self._client.table("dataset_version")
            .select("id,dataset_id,version_no,content_sha256,storage_path,byte_size,created_by")
            .eq("id", str(version_id))
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        version = self._version(rows[0])
        return version if self.get_dataset(workspace_id, version.dataset_id) is not None else None

    def list_versions(self, workspace_id: UUID, dataset_id: UUID) -> list[DatasetVersion]:
        if self.get_dataset(workspace_id, dataset_id) is None:
            return []
        result = (
            self._client.table("dataset_version")
            .select("id,dataset_id,version_no,content_sha256,storage_path,byte_size,created_by")
            .eq("dataset_id", str(dataset_id))
            .order("version_no")
            .execute()
        )
        return [self._version(row) for row in (result.data or [])]


class SupabaseDatasetStorage:
    """Server-side Supabase Storage adapter for private dataset objects."""

    def __init__(self, supabase_client: object, bucket: str = "qros-datasets") -> None:
        self._client = supabase_client
        self._bucket = bucket

    def put(self, storage_path: str, file: BinaryIO) -> None:
        self._client.storage.from_(self._bucket).upload(
            path=storage_path,
            file=file,
            file_options={"upsert": "false"},
        )

    def remove(self, storage_path: str) -> None:
        self._client.storage.from_(self._bucket).remove([storage_path])


def stream_sha256(file: BinaryIO, max_bytes: int) -> tuple[str, int]:
    """Hash a seekable upload while enforcing the server-side byte limit."""
    digest = sha256()
    size = 0
    while True:
        chunk = file.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            raise ValueError("dataset exceeds plan upload limit")
        digest.update(chunk)
    file.seek(0)
    return digest.hexdigest(), size


def storage_path_for(workspace_id: UUID, digest: str, version_no: int) -> str:
    """Return tenant/{tenant_id}/datasets/{sha256(content)}/{version}/."""
    if version_no < 1:
        raise ValueError("version_no must be positive")
    return f"tenant/{workspace_id}/datasets/{digest}/{version_no}/"


__all__ = [
    "Dataset",
    "DatasetStorage",
    "DatasetStore",
    "DatasetVersion",
    "InMemoryDatasetStorage",
    "InMemoryDatasetStore",
    "SupabaseDatasetStorage",
    "SupabaseDatasetStore",
    "storage_path_for",
    "stream_sha256",
]
