"""Idempotency primitives for the QROS SaaS API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Protocol
from uuid import UUID

MAX_IDEMPOTENCY_KEY_LENGTH = 128


@dataclass(frozen=True)
class IdempotencyRecord:
    workspace_id: UUID
    key: str
    request_fingerprint: str
    status_code: int
    response_body: dict[str, Any]


class IdempotencyConflict(ValueError):
    """The same tenant/key was reused for a different request."""


class IdempotencyStore(Protocol):
    def get(self, workspace_id: UUID, key: str) -> IdempotencyRecord | None:
        ...

    def put(self, record: IdempotencyRecord) -> None:
        ...


class InMemoryIdempotencyStore:
    """Development/test-only idempotency store."""

    def __init__(self) -> None:
        self._records: dict[tuple[UUID, str], IdempotencyRecord] = {}
        self._lock = Lock()

    def get(self, workspace_id: UUID, key: str) -> IdempotencyRecord | None:
        with self._lock:
            return self._records.get((workspace_id, key))

    def put(self, record: IdempotencyRecord) -> None:
        if not record.key or len(record.key) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise ValueError("invalid idempotency key")
        with self._lock:
            existing = self._records.get((record.workspace_id, record.key))
            if existing is not None and existing.request_fingerprint != record.request_fingerprint:
                raise IdempotencyConflict("idempotency key reused with different request")
            self._records[(record.workspace_id, record.key)] = record


class SupabaseIdempotencyStore:
    """Persistent idempotency store backed by public.api_idempotency."""

    def __init__(self, supabase_client: Any) -> None:
        self._client = supabase_client

    @staticmethod
    def _row_to_record(row: dict[str, Any]) -> IdempotencyRecord:
        return IdempotencyRecord(
            workspace_id=UUID(str(row["workspace_id"])),
            key=str(row["key"]),
            request_fingerprint=str(row["request_fingerprint"]),
            status_code=int(row["status_code"]),
            response_body=dict(row["response_body"]),
        )

    def get(self, workspace_id: UUID, key: str) -> IdempotencyRecord | None:
        result = (
            self._client.table("api_idempotency")
            .select("workspace_id,key,request_fingerprint,status_code,response_body")
            .eq("workspace_id", str(workspace_id))
            .eq("key", key)
            .gt("expires_at", datetime.now(timezone.utc).isoformat())
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return self._row_to_record(rows[0]) if rows else None

    def put(self, record: IdempotencyRecord) -> None:
        if not record.key or len(record.key) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise ValueError("invalid idempotency key")
        payload = {
            "workspace_id": str(record.workspace_id),
            "key": record.key,
            "request_fingerprint": record.request_fingerprint,
            "status_code": record.status_code,
            "response_body": record.response_body,
        }
        try:
            self._client.table("api_idempotency").insert(payload).execute()
        except Exception as exc:
            if getattr(exc, "code", None) != "23505":
                raise
            existing = self.get(record.workspace_id, record.key)
            if existing is None:
                raise
            if existing.request_fingerprint != record.request_fingerprint:
                raise IdempotencyConflict("idempotency key reused with different request")
            return


__all__ = [
    "IdempotencyConflict",
    "IdempotencyRecord",
    "IdempotencyStore",
    "InMemoryIdempotencyStore",
    "MAX_IDEMPOTENCY_KEY_LENGTH",
    "SupabaseIdempotencyStore",
]
