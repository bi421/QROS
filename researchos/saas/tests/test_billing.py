import hashlib
import hmac
import json

import pytest

from researchos.saas.billing import (
    BillingEvent,
    BillingEventConflict,
    BillingSignatureError,
    SupabaseBillingEventStore,
    parse_billing_event,
    verify_hmac_signature,
    verify_stripe_signature,
)


class PostgrestError(Exception):
    def __init__(self, code):
        self.code = code


class TableQuery:
    def __init__(self, name, *, rows=None, insert_error=None):
        self.name = name
        self.rows = rows or []
        self.insert_error = insert_error
        self.operation = None
        self.payload = None

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        return self

    def select(self, *_):
        self.operation = "select"
        return self

    def upsert(self, payload, **_):
        self.operation = "upsert"
        self.payload = payload
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        return self

    def eq(self, *_):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        if self.operation == "insert" and self.insert_error is not None:
            raise self.insert_error
        return type("Response", (), {"data": self.rows})()


class BillingClient:
    def __init__(self, *, billing_rows=None, insert_error=None):
        self.tables = {
            "billing_event": TableQuery(
                "billing_event", rows=billing_rows, insert_error=insert_error
            ),
            "subscription": TableQuery("subscription"),
        }

    def table(self, name):
        return self.tables[name]


def _event() -> BillingEvent:
    return BillingEvent(
        event_id="evt_1",
        workspace_id="workspace-1",
        plan="pro",
        status="active",
        current_period_end=None,
    )


def test_billing_signature_is_verified() -> None:
    body = b'{"event_id":"evt_1","workspace_id":"w","plan":"pro","status":"active"}'
    sig = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    verify_hmac_signature(body, sig, "secret")


def test_billing_signature_rejects_tampering() -> None:
    with pytest.raises(BillingSignatureError):
        verify_hmac_signature(b"bad", "00", "secret")


def test_billing_event_requires_identity_and_entitlement() -> None:
    with pytest.raises(ValueError):
        parse_billing_event(json.dumps({"event_id": "x"}).encode())


def test_supabase_billing_store_propagates_non_unique_insert_errors() -> None:
    client = BillingClient(insert_error=PostgrestError("42501"))
    store = SupabaseBillingEventStore(client)

    with pytest.raises(PostgrestError):
        store.process(_event(), "test", "a" * 64)


def test_supabase_billing_store_rejects_same_event_with_different_payload() -> None:
    client = BillingClient(
        billing_rows=[{
            "event_id": "evt_1",
            "payload_sha256": "b" * 64,
            "processed_at": "2026-09-18T00:00:00+00:00",
        }],
        insert_error=PostgrestError("23505"),
    )
    store = SupabaseBillingEventStore(client)

    with pytest.raises(BillingEventConflict):
        store.process(_event(), "test", "a" * 64)


def test_supabase_billing_store_replays_identical_processed_event() -> None:
    client = BillingClient(
        billing_rows=[{
            "event_id": "evt_1",
            "payload_sha256": "a" * 64,
            "processed_at": "2026-09-18T00:00:00+00:00",
        }],
        insert_error=PostgrestError("23505"),
    )
    store = SupabaseBillingEventStore(client)

    assert store.process(_event(), "test", "a" * 64) is False


def test_stripe_signature_verification_accepts_valid_timestamped_signature() -> None:
    import time
    body = b'{"id":"evt_stripe_1","type":"customer.subscription.updated"}'
    timestamp = int(time.time())
    signed = f"{timestamp}.".encode() + body
    signature = hmac.new(b"secret", signed, hashlib.sha256).hexdigest()
    verify_stripe_signature(body, f"t={timestamp},v1={signature}", "secret", now=timestamp)


def test_stripe_signature_rejects_replay_timestamp() -> None:
    with pytest.raises(BillingSignatureError):
        verify_stripe_signature(b"{}", "t=1,v1=00", "secret", now=1000)
