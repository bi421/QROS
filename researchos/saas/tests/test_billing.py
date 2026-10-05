import hashlib
import hmac
import json

import pytest

from researchos.saas.billing import (
    BillingEvent,
    BillingSignatureError,
    SupabaseBillingEventStore,
    parse_billing_event,
    verify_hmac_signature,
    verify_stripe_signature,
)


class RpcQuery:
    def __init__(self, data):
        self.data = data
        self.payload = None

    def execute(self):
        return type("Response", (), {"data": self.data})()


class BillingClient:
    def __init__(self, *, rpc_result=True):
        self.rpc_result = rpc_result
        self.rpc_name = None
        self.rpc_payload = None

    def rpc(self, name, payload):
        self.rpc_name = name
        self.rpc_payload = payload
        return RpcQuery(self.rpc_result)



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


def test_supabase_billing_store_uses_atomic_rpc() -> None:
    client = BillingClient()
    store = SupabaseBillingEventStore(client)

    assert store.process(_event(), "stripe", "a" * 64) is True
    assert client.rpc_name == "process_billing_event"
    assert client.rpc_payload["p_event_id"] == "evt_1"
    assert client.rpc_payload["p_workspace_id"] == "workspace-1"
    assert client.rpc_payload["p_payload_sha256"] == "a" * 64
    assert client.rpc_payload["p_provider_customer_id"] is None
    assert client.rpc_payload["p_provider_subscription_id"] is None
    assert client.rpc_payload["p_event_created_at"] is None


def test_supabase_billing_store_returns_duplicate_result() -> None:
    client = BillingClient(rpc_result=False)
    store = SupabaseBillingEventStore(client)

    assert store.process(_event(), "stripe", "a" * 64) is False


def test_supabase_billing_store_rejects_invalid_rpc_result() -> None:
    client = BillingClient(rpc_result={"processed": True})
    store = SupabaseBillingEventStore(client)

    with pytest.raises(RuntimeError, match="invalid result"):
        store.process(_event(), "stripe", "a" * 64)



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


def test_parse_stripe_subscription_event_maps_price_id_to_plan() -> None:
    payload = {
        "id": "evt_sub_1",
        "data": {
            "object": {
                "metadata": {"workspace_id": "workspace-1"},
                "status": "active",
                "items": {"data": [{"price": {"id": "price_pro"}}]},
            }
        },
    }
    event = parse_billing_event(
        json.dumps(payload).encode(),
        plan_by_price_id={"price_pro": "pro"},
    )
    assert event.plan == "pro"
    assert event.workspace_id == "workspace-1"


def test_parse_stripe_subscription_event_persists_provider_ids_and_normalizes_epoch() -> None:
    payload = {
        "id": "evt_sub_ids",
        "type": "customer.subscription.updated",
        "created": 1790812800,
        "data": {
            "object": {
                "id": "sub_123",
                "customer": "cus_123",
                "metadata": {"workspace_id": "workspace-1", "plan": "pro"},
                "status": "active",
                "current_period_end": 1790812800,
            }
        },
    }
    event = parse_billing_event(
        json.dumps(payload).encode(),
        require_stripe_subscription_event=True,
    )
    assert event.provider_customer_id == "cus_123"
    assert event.provider_subscription_id == "sub_123"
    assert event.current_period_end == "2026-10-31T00:00:00+00:00"
    assert event.event_created_at == "2026-10-31T00:00:00+00:00"


def test_parse_billing_event_rejects_unmapped_price_id() -> None:
    payload = {
        "id": "evt_sub_2",
        "data": {
            "object": {
                "metadata": {"workspace_id": "workspace-1"},
                "status": "active",
                "items": {"data": [{"price": {"id": "price_unknown"}}]},
            }
        },
    }
    with pytest.raises(ValueError):
        parse_billing_event(
            json.dumps(payload).encode(),
            plan_by_price_id={"price_pro": "pro"},
        )


def test_parse_stripe_subscription_event_rejects_checkout_events() -> None:
    payload = {
        "id": "evt_checkout_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"workspace_id": "workspace-1", "plan": "pro"},
                "status": "complete",
            }
        },
    }
    with pytest.raises(ValueError, match="unsupported Stripe billing event type"):
        parse_billing_event(
            json.dumps(payload).encode(),
            require_stripe_subscription_event=True,
        )


def test_parse_deleted_stripe_subscription_without_status_fails_closed() -> None:
    payload = {
        "id": "evt_deleted_1",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "metadata": {"workspace_id": "workspace-1", "plan": "pro"},
            }
        },
    }
    event = parse_billing_event(
        json.dumps(payload).encode(),
        require_stripe_subscription_event=True,
    )
    assert event.status == "cancelled"
