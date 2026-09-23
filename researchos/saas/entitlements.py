"""Tenant plan entitlements and usage enforcement."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from researchos.saas.contracts import Plan


@dataclass(frozen=True)
class Entitlement:
    tenant_id: UUID
    plan: str
    max_datasets: int
    max_jobs_per_month: int
    max_storage_mb: int
    max_members: int

    def limit(self, name: str) -> int:
        return int(getattr(self, name))


DEFAULT_ENTITLEMENTS: dict[str, Entitlement] = {
    "free": Entitlement(UUID(int=0), "free", 3, 100, 1024, 5),
    "pro": Entitlement(UUID(int=0), "pro", 100, 1000, 102400, 50),
    "enterprise": Entitlement(UUID(int=0), "enterprise", 0, 0, 0, 0),
}


class EntitlementStore(Protocol):
    def get(self, tenant_id: UUID, plan: Plan) -> Entitlement: ...


class InMemoryEntitlementStore:
    def __init__(self) -> None:
        self._rows: dict[UUID, Entitlement] = {}

    def set(self, entitlement: Entitlement) -> None:
        self._rows[entitlement.tenant_id] = entitlement

    def get(self, tenant_id: UUID, plan: Plan) -> Entitlement:
        existing = self._rows.get(tenant_id)
        if existing is not None:
            return existing
        template = DEFAULT_ENTITLEMENTS.get(plan.value, DEFAULT_ENTITLEMENTS["free"])
        return Entitlement(tenant_id, template.plan, template.max_datasets, template.max_jobs_per_month, template.max_storage_mb, template.max_members)


class SupabaseEntitlementStore:
    def __init__(self, supabase_client: Any) -> None:
        self._client = supabase_client

    def get(self, tenant_id: UUID, plan: Plan) -> Entitlement:
        result = (
            self._client.table("entitlements")
            .select("tenant_id,plan,max_datasets,max_jobs_per_month,max_storage_mb,max_members")
            .eq("tenant_id", str(tenant_id))
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            template = DEFAULT_ENTITLEMENTS.get(plan.value, DEFAULT_ENTITLEMENTS["free"])
            return Entitlement(tenant_id, template.plan, template.max_datasets, template.max_jobs_per_month, template.max_storage_mb, template.max_members)
        row = rows[0]
        return Entitlement(
            tenant_id=UUID(str(row["tenant_id"])),
            plan=str(row["plan"]),
            max_datasets=int(row["max_datasets"]),
            max_jobs_per_month=int(row["max_jobs_per_month"]),
            max_storage_mb=int(row["max_storage_mb"]),
            max_members=int(row["max_members"]),
        )


@dataclass(frozen=True)
class UsageSnapshot:
    datasets: int = 0
    jobs_this_month: int = 0
    storage_mb: int = 0
    members: int = 0


def exceeded(entitlement: Entitlement, usage: UsageSnapshot) -> str | None:
    checks = (
        ("max_datasets", usage.datasets),
        ("max_jobs_per_month", usage.jobs_this_month),
        ("max_storage_mb", usage.storage_mb),
        ("max_members", usage.members),
    )
    for field, used in checks:
        limit = entitlement.limit(field)
        if limit > 0 and used >= limit:
            return field
    return None


__all__ = [
    "DEFAULT_ENTITLEMENTS",
    "Entitlement",
    "EntitlementStore",
    "InMemoryEntitlementStore",
    "SupabaseEntitlementStore",
    "UsageSnapshot",
    "exceeded",
]
