"""Tenant-scoped dataset persistence, immutable versions, and content-addressed storage."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, BinaryIO, Protocol
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
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


class DatasetReferencedError(RuntimeError):
    """Raised when retention policy prevents dataset deletion."""


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
    def count_datasets(self, workspace_id: UUID) -> int: ...
    def storage_bytes(self, workspace_id: UUID) -> int: ...


class DatasetStorage(Protocol):
    def put(self, storage_path: str, file: BinaryIO, *, tenant_id: UUID | None = None, access_token: str | None = None) -> None: ...
    def remove(self, storage_path: str, *, tenant_id: UUID | None = None, access_token: str | None = None) -> None: ...
    def create_signed_download_url(self, storage_path: str, expires_in: int, *, tenant_id: UUID | None = None, access_token: str | None = None) -> str: ...
    def verify_sha256(self, storage_path: str, expected_sha256: str, *, tenant_id: UUID | None = None, access_token: str | None = None) -> bool: ...


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
        if version.storage_path != storage_path_for(workspace_id, version.content_sha256, version.version_no):
            raise ValueError("dataset storage path does not match canonical content-addressed path")
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


    def count_datasets(self, workspace_id: UUID) -> int:
        return sum(dataset.workspace_id == workspace_id for dataset in self._datasets.values())

    def storage_bytes(self, workspace_id: UUID) -> int:
        return sum(version.byte_size for version in self._versions.values() if self.get_dataset(workspace_id, version.dataset_id) is not None)

class InMemoryDatasetStorage:
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def put(self, storage_path: str, file: BinaryIO, *, tenant_id: UUID | None = None, access_token: str | None = None) -> None:
        if tenant_id is not None and not storage_path.startswith(f"tenant/{tenant_id}/"):
            raise PermissionError("storage path is outside tenant context")
        payload = file.read()
        existing = self._objects.get(storage_path)
        if existing is not None:
            if existing != payload:
                raise ValueError("storage object already exists with different content")
            file.seek(0)
            return
        self._objects[storage_path] = payload
        file.seek(0)

    def remove(self, storage_path: str, *, tenant_id: UUID | None = None, access_token: str | None = None) -> None:
        if tenant_id is not None and not storage_path.startswith(f"tenant/{tenant_id}/"):
            raise PermissionError("storage path is outside tenant context")
        self._objects.pop(storage_path, None)

    def get(self, storage_path: str) -> bytes | None:
        return self._objects.get(storage_path)

    def verify_sha256(self, storage_path: str, expected_sha256: str, *, tenant_id: UUID | None = None, access_token: str | None = None) -> bool:
        if tenant_id is not None and not storage_path.startswith(f"tenant/{tenant_id}/"):
            raise PermissionError("storage path is outside tenant context")
        payload = self._objects.get(storage_path)
        return payload is not None and sha256(payload).hexdigest() == expected_sha256.lower()

    def create_signed_download_url(self, storage_path: str, expires_in: int, *, tenant_id: UUID | None = None, access_token: str | None = None) -> str:
        if tenant_id is not None and not storage_path.startswith(f"tenant/{tenant_id}/"):
            raise PermissionError("storage path is outside tenant context")
        if storage_path not in self._objects:
            raise FileNotFoundError(storage_path)
        if expires_in != 3600:
            raise ValueError("dataset signed URL expiry must be exactly 3600 seconds")
        return f"memory://{storage_path}?expires_in=3600"


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
        try:
            self._client.table("dataset").delete().eq("id", str(dataset_id)).eq("workspace_id", str(workspace_id)).execute()
        except Exception as exc:
            if "DATASET_REFERENCED" in str(exc):
                raise DatasetReferencedError("DATASET_REFERENCED") from exc
            raise

    def create_version(self, workspace_id: UUID, version: DatasetVersion) -> DatasetVersion:
        if version.storage_path != storage_path_for(workspace_id, version.content_sha256, version.version_no):
            raise ValueError("dataset storage path does not match canonical content-addressed path")
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


    def count_datasets(self, workspace_id: UUID) -> int:
        _, total = self.list_datasets(workspace_id, limit=1, offset=0)
        return total

    def storage_bytes(self, workspace_id: UUID) -> int:
        result = self._client.table("dataset_version").select("byte_size", count="exact").execute()
        rows = result.data or []
        total = 0
        for row in rows:
            version = self._version(row)
            if self.get_dataset(workspace_id, version.dataset_id) is not None:
                total += version.byte_size
        return total

class SupabaseDatasetStorage:
    """Tenant-scoped Supabase Storage adapter.

    Production calls require a verified tenant bearer token so Storage RLS,
    rather than service_role, authorizes object access.
    """

    def __init__(
        self,
        supabase_client: object,
        bucket: str = "qros-datasets",
        *,
        supabase_url: str | None = None,
        publishable_key: str | None = None,
    ) -> None:
        self._client = supabase_client
        self._bucket = bucket
        self._supabase_url = supabase_url
        self._publishable_key = publishable_key

    @staticmethod
    def _tenant_path(tenant_id: UUID, storage_path: str) -> str:
        expected = f"tenant/{tenant_id}/"
        if not storage_path.startswith(expected):
            raise PermissionError("storage path is outside tenant context")
        return storage_path

    def _request(self, method: str, path: str, *, tenant_id: UUID, access_token: str, body: bytes | None = None) -> bytes:
        if not access_token:
            raise PermissionError("tenant access token is required for storage access")
        if not self._supabase_url or not self._publishable_key:
            raise RuntimeError("tenant-scoped Supabase Storage requires SUPABASE_URL and SUPABASE_ANON_KEY")
        self._tenant_path(tenant_id, path)
        url = f"{self._supabase_url.rstrip('/')}/storage/v1/object/{self._bucket}/{quote(path, safe='')}"
        headers = {
            "apikey": self._publishable_key,
            "Authorization": f"Bearer {access_token}",
        }
        if body is not None:
            headers["Content-Type"] = "application/octet-stream"
        request = Request(url, data=body, headers=headers, method=method)
        with urlopen(request, timeout=30) as response:
            return response.read()

    def put(self, storage_path: str, file: BinaryIO, *, tenant_id: UUID | None = None, access_token: str | None = None) -> None:
        if tenant_id is not None and access_token is not None:
            self._request("POST", storage_path, tenant_id=tenant_id, access_token=access_token, body=file.read())
            file.seek(0)
            return
        raise PermissionError("tenant context is required for production storage writes")

    def remove(self, storage_path: str, *, tenant_id: UUID | None = None, access_token: str | None = None) -> None:
        if tenant_id is None or access_token is None:
            raise PermissionError("tenant context is required for production storage deletes")
        self._request("DELETE", storage_path, tenant_id=tenant_id, access_token=access_token)

    def verify_sha256(self, storage_path: str, expected_sha256: str, *, tenant_id: UUID | None = None, access_token: str | None = None) -> bool:
        if tenant_id is None or access_token is None:
            raise PermissionError("tenant context is required for production storage reads")
        payload = self._request("GET", storage_path, tenant_id=tenant_id, access_token=access_token)
        return sha256(payload).hexdigest() == expected_sha256.lower()

    def create_signed_download_url(
        self,
        storage_path: str,
        expires_in: int,
        *,
        tenant_id: UUID | None = None,
        access_token: str | None = None,
    ) -> str:
        if expires_in != 3600:
            raise ValueError("dataset signed URL expiry must be exactly 3600 seconds")
        if tenant_id is None or access_token is None:
            raise PermissionError("tenant context is required for signed URLs")
        self._tenant_path(tenant_id, storage_path)
        if not self._supabase_url or not self._publishable_key:
            raise RuntimeError("tenant-scoped Supabase Storage requires SUPABASE_URL and SUPABASE_ANON_KEY")
        url = f"{self._supabase_url.rstrip('/')}/storage/v1/object/sign/{self._bucket}/{quote(storage_path, safe='')}"
        request = Request(
            url,
            data=b'{"expiresIn":3600}',
            headers={
                "apikey": self._publishable_key,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            payload = response.read()
        import json
        data = json.loads(payload.decode("utf-8"))
        signed_url = data.get("signedURL") or data.get("signedUrl")
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
    if len(digest) != 64 or digest != digest.lower() or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("content_sha256 must be a 64-character SHA-256 digest")
    if version_no < 1:
        raise ValueError("version_no must be positive")
    return f"tenant/{workspace_id}/datasets/{digest.lower()}/{version_no}/"


__all__ = [
    "Dataset", "DatasetReferencedError", "DatasetStorage", "DatasetStore", "DatasetVersion",
    "InMemoryDatasetStorage", "InMemoryDatasetStore", "SupabaseDatasetStorage",
    "SupabaseDatasetStore", "storage_path_for", "stream_sha256",
]
