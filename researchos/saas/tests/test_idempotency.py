from uuid import uuid4

import pytest

from researchos.saas.idempotency import (
    IdempotencyConflict,
    IdempotencyRecord,
    SupabaseIdempotencyStore,
)


class Query:
    def __init__(self, rows=None, *, insert_error=None):
        self.rows = rows or []
        self.insert_error = insert_error
        self.inserted = None

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def gt(self, *_):
        return self

    def limit(self, *_):
        return self

    def insert(self, payload):
        self.inserted = payload
        return self

    def execute(self):
        if self.insert_error is not None and self.inserted is not None:
            raise self.insert_error
        return type("Response", (), {"data": self.rows})()


class Client:
    def __init__(self, rows=None, *, insert_error=None):
        self.query = Query(rows, insert_error=insert_error)

    def table(self, name):
        assert name == "api_idempotency"
        return self.query


def _record(fingerprint="a" * 64):
    return IdempotencyRecord(
        workspace_id=uuid4(),
        key="research-1",
        request_fingerprint=fingerprint,
        status_code=202,
        response_body={"id": str(uuid4()), "status": "queued"},
    )


def test_supabase_idempotency_store_round_trips_record() -> None:
    record = _record()
    client = Client(
        rows=[{
            "workspace_id": str(record.workspace_id),
            "key": record.key,
            "request_fingerprint": record.request_fingerprint,
            "status_code": record.status_code,
            "response_body": record.response_body,
        }]
    )
    store = SupabaseIdempotencyStore(client)

    assert store.get(record.workspace_id, record.key) == record
    store.put(record)
    assert client.query.inserted["workspace_id"] == str(record.workspace_id)


def test_supabase_idempotency_store_detects_conflicting_concurrent_key() -> None:
    record = _record()
    existing = _record("b" * 64)
    existing = IdempotencyRecord(
        workspace_id=record.workspace_id,
        key=record.key,
        request_fingerprint=existing.request_fingerprint,
        status_code=existing.status_code,
        response_body=existing.response_body,
    )
    client = Client(
        rows=[{
            "workspace_id": str(existing.workspace_id),
            "key": existing.key,
            "request_fingerprint": existing.request_fingerprint,
            "status_code": existing.status_code,
            "response_body": existing.response_body,
        }],
        insert_error=type("PostgrestError", (), {"code": "23505"})(),
    )

    with pytest.raises(IdempotencyConflict):
        SupabaseIdempotencyStore(client).put(record)
