"""Provider-neutral billing webhook boundary."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class BillingEvent:
    event_id: str
    workspace_id: str
    plan: str
    status: str
    current_period_end: str | None



@dataclass(frozen=True)
class Entitlement:
    tenant_id: UUID
    plan: str
    max_datasets: int
    max_jobs_per_month: int
    max_storage_mb: int

    def allows_jobs(self, used: int) -> bool:
        return self.max_jobs_per_month == 0 or used < self.max_jobs_per_month


ENTITLEMENTS_BY_PLAN: dict[str, tuple[int, int, int]] = {
    "free": (10, 100, 1024),
    "pro": (1000, 1000, 10240),
    "enterprise": (0, 0, 0),
}


class EntitlementStore(Protocol):
    def get(self, tenant_id: UUID, plan: str) -> Entitlement: ...
    def upsert(self, entitlement: Entitlement) -> Entitlement: ...


class InMemoryEntitlementStore:
    def __init__(self) -> None:
        self._rows: dict[UUID, Entitlement] = {}

    def get(self, tenant_id: UUID, plan: str) -> Entitlement:
        existing = self._rows.get(tenant_id)
        if existing is not None:
            return existing
        limits = ENTITLEMENTS_BY_PLAN[plan]
        return Entitlement(tenant_id, plan, *limits)

    def upsert(self, entitlement: Entitlement) -> Entitlement:
        self._rows[entitlement.tenant_id] = entitlement
        return entitlement


class SupabaseEntitlementStore:
    def __init__(self, supabase_client: Any) -> None:
        self._client = supabase_client

    def get(self, tenant_id: UUID, plan: str) -> Entitlement:
        result = self._client.table("entitlement").select("tenant_id,plan,max_datasets,max_jobs_per_month,max_storage_mb").eq("tenant_id", str(tenant_id)).limit(1).execute()
        rows = result.data or []
        if rows:
            row = rows[0]
            return Entitlement(UUID(str(row["tenant_id"])), str(row["plan"]), int(row["max_datasets"]), int(row["max_jobs_per_month"]), int(row["max_storage_mb"]))
        return Entitlement(tenant_id, plan, *ENTITLEMENTS_BY_PLAN[plan])

    def upsert(self, entitlement: Entitlement) -> Entitlement:
        self._client.table("entitlement").upsert({"tenant_id": str(entitlement.tenant_id), "plan": entitlement.plan, "max_datasets": entitlement.max_datasets, "max_jobs_per_month": entitlement.max_jobs_per_month, "max_storage_mb": entitlement.max_storage_mb, "updated_at": datetime.now(timezone.utc).isoformat()}, on_conflict="tenant_id").execute()
        return entitlement


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

        max_datasets, max_jobs, max_storage = ENTITLEMENTS_BY_PLAN[event.plan]
        self._client.table("entitlement").upsert({"tenant_id": event.workspace_id, "plan": event.plan, "max_datasets": max_datasets, "max_jobs_per_month": max_jobs, "max_storage_mb": max_storage, "updated_at": datetime.now(timezone.utc).isoformat()}, on_conflict="tenant_id").execute()
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


def verify_stripe_signature(payload: bytes, signature: str, secret: str, *, tolerance_seconds: int = 300, now: int | None = None) -> None:
    parts: dict[str, list[str]] = {}
    for item in signature.split(","):
        key, sep, value = item.strip().partition("=")
        if sep:
            parts.setdefault(key, []).append(value)
    try:
        timestamp = int(parts["t"][0])
        provided = parts["v1"]
    except (KeyError, ValueError, IndexError) as exc:
        raise BillingSignatureError("invalid Stripe webhook signature") from exc
    current = int(datetime.now(timezone.utc).timestamp()) if now is None else now
    if abs(current - timestamp) > tolerance_seconds:
        raise BillingSignatureError("Stripe webhook signature timestamp outside tolerance")
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in provided):
        raise BillingSignatureError("invalid Stripe webhook signature")


def verify_hmac_signature(payload: bytes, signature: str, secret: str) -> None:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.strip()):
        raise BillingSignatureError("invalid billing webhook signature")


def parse_billing_event(payload: bytes) -> BillingEvent:
    data: dict[str, Any] = json.loads(payload)
    event_id = data.get("event_id") or data.get("id")
    obj = data.get("data", {}).get("object", {}) if isinstance(data.get("data"), dict) else {}
    metadata = obj.get("metadata", {}) if isinstance(obj, dict) else {}
    workspace_id = data.get("workspace_id") or metadata.get("workspace_id") or obj.get("workspace_id")
    plan = data.get("plan") or metadata.get("plan") or obj.get("plan")
    status = data.get("status") or obj.get("status") or "active"
    if not all(str(value or "").strip() for value in (event_id, workspace_id, plan)):
        raise ValueError("billing event missing required fields")
    if str(plan) not in ENTITLEMENTS_BY_PLAN:
        raise ValueError("unsupported billing entitlement plan")
    return BillingEvent(str(event_id), str(workspace_id), str(plan), str(status), data.get("current_period_end") or obj.get("current_period_end"))


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
