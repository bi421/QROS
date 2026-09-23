"""Tenant-scoped dataset persistence, immutable versions, and content-addressed storage."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, BinaryIO, Protocol
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
    feeds: tuple[str, ...] = ()


class DatasetStore(Protocol):
    def list_datasets(self, workspace_id: UUID, *, limit: int = 50, offset: int = 0, name_filter: str | None = None) -> tuple[list[Dataset], int]: ...
    def create_dataset(self, workspace_id: UUID, dataset: Dataset) -> Dataset: ...
    def delete_dataset(self, workspace_id: UUID, dataset_id: UUID) -> None: ...
    def create_version(self, workspace_id: UUID, version: DatasetVersion) -> DatasetVersion: ...
    def find_version_by_content(self, workspace_id: UUID, dataset_id: UUID, content_sha256: str) -> DatasetVersion | None: ...
    def next_version_no(self, workspace_id: UUID, dataset_id: UUID) -> int: ...
    def link_experiment(self, workspace_id: UUID, version_id: UUID, experiment_id: str) -> DatasetVersion: ...
    def get_dataset(self, workspace_id: UUID, dataset_id: UUID) -> Dataset | None: ...
    def get_version(self, workspace_id: UUID, version_id: UUID) -> DatasetVersion | None: ...
    def list_versions(self, workspace_id: UUID, dataset_id: UUID) -> list[DatasetVersion]: ...


class DatasetStorage(Protocol):
    def put(self, storage_path: str, file: BinaryIO) -> None: ...
    def remove(self, storage_path: str) -> None: ...
    def create_signed_download_url(self, storage_path: str, expires_in: int) -> str: ...
    def verify_sha256(self, storage_path: str, expected_sha256: str) -> bool: ...


class InMemoryDatasetStore:
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

    def list_datasets(self, workspace_id: UUID, *, limit: int = 50, offset: int = 0, name_filter: str | None = None) -> tuple[list[Dataset], int]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("invalid pagination")
        needle = name_filter.strip().lower() if name_filter else None
        rows = [d for d in self._datasets.values() if d.workspace_id == workspace_id and (needle is None or needle in d.name.lower())]
        rows.sort(key=lambda item: item.id.hex)
        return rows[offset:offset + limit], len(rows)

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

    def find_version_by_content(self, workspace_id: UUID, dataset_id: UUID, content_sha256: str) -> DatasetVersion | None:
        if self.get_dataset(workspace_id, dataset_id) is None:
            return None
        return next((v for v in self._versions.values() if v.dataset_id == dataset_id and v.content_sha256 == content_sha256), None)

    def next_version_no(self, workspace_id: UUID, dataset_id: UUID) -> int:
        if self.get_dataset(workspace_id, dataset_id) is None:
            raise KeyError("dataset not found for workspace")
        return max((v.version_no for v in self._versions.values() if v.dataset_id == dataset_id), default=0) + 1

    def link_experiment(self, workspace_id: UUID, version_id: UUID, experiment_id: str) -> DatasetVersion:
        version = self.get_version(workspace_id, version_id)
        if version is None:
            raise KeyError("dataset version not found for workspace")
        updated = DatasetVersion(
            version.id, version.dataset_id, version.version_no, version.content_sha256,
            version.storage_path, version.byte_size, version.created_by,
            tuple(sorted(set(version.feeds) | {experiment_id})),
        )
        self._versions[version_id] = updated
        return updated

    def get_dataset(self, workspace_id: UUID, dataset_id: UUID) -> Dataset | None:
        dataset = self._datasets.get(dataset_id)
        return dataset if dataset is not None and dataset.workspace_id == workspace_id else None

    def get_version(self, workspace_id: UUID, version_id: UUID) -> DatasetVersion | None:
        version = self._versions.get(version_id)
        if version is None or self.get_dataset(workspace_id, version.dataset_id) is None:
            return None
        return version

    def list_versions(self, workspace_id: UUID, dataset_id: UUID) -> list[DatasetVersion]:
        if self.get_dataset(workspace_id, dataset_id) is None:
            return []
        return sorted((v for v in self._versions.values() if v.dataset_id == dataset_id), key=lambda v: v.version_no)


class InMemoryDatasetStorage:
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def put(self, storage_path: str, file: BinaryIO) -> None:
        payload = file.read()
        existing = self._objects.get(storage_path)
        if existing is not None:
            if existing != payload:
                raise ValueError("storage object already exists with different content")
            file.seek(0)
            return
        self._objects[storage_path] = payload
        file.seek(0)

    def remove(self, storage_path: str) -> None:
        self._objects.pop(storage_path, None)

    def get(self, storage_path: str) -> bytes | None:
        return self._objects.get(storage_path)

    def verify_sha256(self, storage_path: str, expected_sha256: str) -> bool:
        payload = self._objects.get(storage_path)
        return payload is not None and sha256(payload).hexdigest() == expected_sha256.lower()

    def create_signed_download_url(self, storage_path: str, expires_in: int) -> str:
        if storage_path not in self._objects:
            raise FileNotFoundError(storage_path)
        if not 1 <= expires_in <= 900:
            raise ValueError("signed URL expiry must be between 1 and 900 seconds")
        return f"memory://{storage_path}?expires_in={expires_in}"


class SupabaseDatasetStore:
    def __init__(self, supabase_client: Any) -> None:
        self._client = supabase_client

    @staticmethod
    def _dataset(row: dict[str, object]) -> Dataset:
        return Dataset(UUID(str(row["id"])), UUID(str(row["workspace_id"])), str(row["name"]), UUID(str(row["created_by"])))

    @staticmethod
    def _version(row: dict[str, object], feeds: tuple[str, ...] = ()) -> DatasetVersion:
        return DatasetVersion(
            UUID(str(row["id"])), UUID(str(row["dataset_id"])), int(row["version_no"]),
            str(row["content_sha256"]), str(row["storage_path"]), int(row["byte_size"]),
            UUID(str(row["created_by"])), feeds,
        )

    def create_dataset(self, workspace_id: UUID, dataset: Dataset) -> Dataset:
        if dataset.workspace_id != workspace_id:
            raise ValueError("dataset workspace does not match tenant")
        result = self._client.table("dataset").insert({
            "id": str(dataset.id), "workspace_id": str(dataset.workspace_id),
            "name": dataset.name, "created_by": str(dataset.created_by),
        }).select("id,workspace_id,name,created_by").execute()
        rows = result.data or []
        if len(rows) != 1:
            raise RuntimeError("dataset insert returned no unique row")
        return self._dataset(rows[0])

    def list_datasets(self, workspace_id: UUID, *, limit: int = 50, offset: int = 0, name_filter: str | None = None) -> tuple[list[Dataset], int]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("invalid pagination")
        query = self._client.table("dataset").select("id,workspace_id,name,created_by", count="exact").eq("workspace_id", str(workspace_id))
        if name_filter:
            query = query.ilike("name", f"%{name_filter.strip()}%")
        result = query.order("id").range(offset, offset + limit - 1).execute()
        return [self._dataset(row) for row in (result.data or [])], int(result.count or 0)

    def delete_dataset(self, workspace_id: UUID, dataset_id: UUID) -> None:
        self._client.table("dataset").delete().eq("id", str(dataset_id)).eq("workspace_id", str(workspace_id)).execute()

    def create_version(self, workspace_id: UUID, version: DatasetVersion) -> DatasetVersion:
        if self.get_dataset(workspace_id, version.dataset_id) is None:
            raise KeyError("dataset not found for workspace")
        result = self._client.table("dataset_version").insert({
            "id": str(version.id), "dataset_id": str(version.dataset_id),
            "version_no": version.version_no, "content_sha256": version.content_sha256,
            "storage_path": version.storage_path, "byte_size": version.byte_size,
            "created_by": str(version.created_by),
        }).select("id,dataset_id,version_no,content_sha256,storage_path,byte_size,created_by").execute()
        rows = result.data or []
        if len(rows) != 1:
            raise RuntimeError("dataset version insert returned no unique row")
        return self._version(rows[0], version.feeds)

    def find_version_by_content(self, workspace_id: UUID, dataset_id: UUID, content_sha256: str) -> DatasetVersion | None:
        if self.get_dataset(workspace_id, dataset_id) is None:
            return None
        result = self._client.table("dataset_version").select(
            "id,dataset_id,version_no,content_sha256,storage_path,byte_size,created_by"
        ).eq("dataset_id", str(dataset_id)).eq("content_sha256", content_sha256).limit(1).execute()
        rows = result.data or []
        return self._version(rows[0]) if rows else None

    def next_version_no(self, workspace_id: UUID, dataset_id: UUID) -> int:
        versions = self.list_versions(workspace_id, dataset_id)
        if self.get_dataset(workspace_id, dataset_id) is None:
            raise KeyError("dataset not found for workspace")
        return max((v.version_no for v in versions), default=0) + 1

    def link_experiment(self, workspace_id: UUID, version_id: UUID, experiment_id: str) -> DatasetVersion:
        version = self.get_version(workspace_id, version_id)
        if version is None:
            raise KeyError("dataset version not found for workspace")
        self._client.table("dataset_version_feed").upsert(
            {"dataset_version_id": str(version_id), "experiment_id": experiment_id}
        ).execute()
        feeds_result = self._client.table("dataset_version_feed").select("experiment_id").eq(
            "dataset_version_id", str(version_id)
        ).execute()
        feeds = tuple(sorted(str(row["experiment_id"]) for row in (feeds_result.data or [])))
        return DatasetVersion(
            version.id, version.dataset_id, version.version_no, version.content_sha256,
            version.storage_path, version.byte_size, version.created_by, feeds,
        )

    def get_dataset(self, workspace_id: UUID, dataset_id: UUID) -> Dataset | None:
        result = self._client.table("dataset").select("id,workspace_id,name,created_by").eq(
            "id", str(dataset_id)
        ).eq("workspace_id", str(workspace_id)).limit(1).execute()
        rows = result.data or []
        return self._dataset(rows[0]) if rows else None

    def get_version(self, workspace_id: UUID, version_id: UUID) -> DatasetVersion | None:
        result = self._client.table("dataset_version").select(
            "id,dataset_id,version_no,content_sha256,storage_path,byte_size,created_by"
        ).eq("id", str(version_id)).limit(1).execute()
        rows = result.data or []
        if not rows:
            return None
        version = self._version(rows[0])
        return version if self.get_dataset(workspace_id, version.dataset_id) is not None else None

    def list_versions(self, workspace_id: UUID, dataset_id: UUID) -> list[DatasetVersion]:
        if self.get_dataset(workspace_id, dataset_id) is None:
            return []
        result = self._client.table("dataset_version").select(
            "id,dataset_id,version_no,content_sha256,storage_path,byte_size,created_by"
        ).eq("dataset_id", str(dataset_id)).order("version_no").execute()
        return [self._version(row) for row in (result.data or [])]


class SupabaseDatasetStorage:
    def __init__(self, supabase_client: object, bucket: str = "qros-datasets") -> None:
        self._client = supabase_client
        self._bucket = bucket

    def put(self, storage_path: str, file: BinaryIO) -> None:
        self._client.storage.from_(self._bucket).upload(
            path=storage_path, file=file, file_options={"upsert": "false"}
        )

    def remove(self, storage_path: str) -> None:
        self._client.storage.from_(self._bucket).remove([storage_path])

    def verify_sha256(self, storage_path: str, expected_sha256: str) -> bool:
        response = self._client.storage.from_(self._bucket).download(storage_path)
        payload = response if isinstance(response, bytes) else bytes(response)
        return sha256(payload).hexdigest() == expected_sha256.lower()

    def create_signed_download_url(self, storage_path: str, expires_in: int) -> str:
        if not 1 <= expires_in <= 900:
            raise ValueError("signed URL expiry must be between 1 and 900 seconds")
        response = self._client.storage.from_(self._bucket).create_signed_url(storage_path, expires_in)
        if isinstance(response, dict):
            signed_url = response.get("signedURL") or response.get("signedUrl")
        else:
            signed_url = getattr(response, "signedURL", None) or getattr(response, "signedUrl", None)
        if not signed_url:
            raise RuntimeError("storage provider returned no signed download URL")
        return str(signed_url)


def stream_sha256(file: BinaryIO, max_bytes: int) -> tuple[str, int]:
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


def storage_path_for(workspace_id: UUID, digest: str, version_no: int = 1) -> str:
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
        raise ValueError("content_sha256 must be a 64-character SHA-256 digest")
    if version_no < 1:
        raise ValueError("version_no must be positive")
    return f"tenant/{workspace_id}/datasets/{digest.lower()}/{version_no}/"


__all__ = [
    "Dataset", "DatasetStorage", "DatasetStore", "DatasetVersion",
    "InMemoryDatasetStorage", "InMemoryDatasetStore", "SupabaseDatasetStorage",
    "SupabaseDatasetStore", "storage_path_for", "stream_sha256",
]
