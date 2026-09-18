"""Idempotency primitives for the QROS SaaS API."""
from __future__ import annotations
from dataclasses import dataclass
from threading import Lock
from uuid import UUID

MAX_IDEMPOTENCY_KEY_LENGTH = 128

@dataclass(frozen=True)
class IdempotencyRecord:
    workspace_id: UUID
    key: str
    request_fingerprint: str
    status_code: int
    response_body: dict

class IdempotencyConflict(ValueError):
    pass

class InMemoryIdempotencyStore:
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
