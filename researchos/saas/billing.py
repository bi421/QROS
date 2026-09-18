"""Provider-neutral billing webhook boundary."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass(frozen=True)
class BillingEvent:
    event_id: str
    workspace_id: str
    plan: str
    status: str
    current_period_end: str | None


class BillingSignatureError(ValueError):
    pass


class BillingEventConflict(ValueError):
    """A provider reused an event id for different payload bytes."""


class BillingEventStore(Protocol):
    def process(self, event: BillingEvent, provider: str, payload_sha256: str) -> bool:
        """Apply an event once; return False when an identical event was already processed."""


class InMemoryBillingEventStore:
    """Development/test-only billing event store."""

    def __init__(self) -> None:
        self._events: dict[str, tuple[str, BillingEvent]] = {}

    def process(self, event: BillingEvent, provider: str, payload_sha256: str) -> bool:
        existing = self._events.get(event.event_id)
        if existing is not None:
            if existing[0] != payload_sha256:
                raise BillingEventConflict("billing event id reused with different payload")
            return False
        self._events[event.event_id] = (payload_sha256, event)
        return True


class SupabaseBillingEventStore:
    """Persistent billing deduplication plus subscription entitlement update."""

    def __init__(self, supabase_client: Any) -> None:
        self._client = supabase_client

    def process(self, event: BillingEvent, provider: str, payload_sha256: str) -> bool:
        row = {
            "event_id": event.event_id,
            "workspace_id": event.workspace_id,
            "provider": provider,
            "payload_sha256": payload_sha256,
        }
        try:
            self._client.table("billing_event").insert(row).execute()
        except Exception as exc:
            if getattr(exc, "code", None) != "23505":
                raise
            existing = (
                self._client.table("billing_event")
                .select("event_id,payload_sha256,processed_at")
                .eq("event_id", event.event_id)
                .limit(1)
                .execute()
            )
            rows = existing.data or []
            if not rows:
                raise
            if rows[0]["payload_sha256"] != payload_sha256:
                raise BillingEventConflict("billing event id reused with different payload")
            if rows[0].get("processed_at"):
                return False

        self._client.table("subscription").upsert(
            {
                "workspace_id": event.workspace_id,
                "plan": event.plan,
                "status": event.status,
                "provider": provider,
                "current_period_end": event.current_period_end,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="workspace_id",
        ).execute()
        self._client.table("billing_event").update(
            {"processed_at": datetime.now(timezone.utc).isoformat()}
        ).eq("event_id", event.event_id).execute()
        return True


def verify_hmac_signature(payload: bytes, signature: str, secret: str) -> None:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.strip()):
        raise BillingSignatureError("invalid billing webhook signature")


def parse_billing_event(payload: bytes) -> BillingEvent:
    data: dict[str, Any] = json.loads(payload)
    required = ("event_id", "workspace_id", "plan", "status")
    if any(not str(data.get(k, "")).strip() for k in required):
        raise ValueError("billing event missing required fields")
    return BillingEvent(
        str(data["event_id"]),
        str(data["workspace_id"]),
        str(data["plan"]),
        str(data["status"]),
        data.get("current_period_end"),
    )


__all__ = [
    "BillingEvent",
    "BillingEventConflict",
    "BillingEventStore",
    "BillingSignatureError",
    "InMemoryBillingEventStore",
    "SupabaseBillingEventStore",
    "parse_billing_event",
    "verify_hmac_signature",
]
