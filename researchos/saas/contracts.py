"""Application contracts for a multi-tenant ResearchOS SaaS.

No scientific calculation belongs here. These contracts make the product
boundary explicit and give API, workers, and persistence layers one stable
vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class Plan(str, Enum):
    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"


class ResearchJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TenantContext:
    """Authenticated workspace context; never inferred from request payloads."""

    user_id: UUID
    workspace_id: UUID
    plan: Plan


@dataclass(frozen=True)
class UsagePolicy:
    """SaaS limits. A zero value means unlimited for that dimension."""

    monthly_research_runs: int
    max_dataset_bytes: int
    max_concurrent_runs: int

    def allows_dataset(self, size_bytes: int) -> bool:
        return size_bytes >= 0 and (
            self.max_dataset_bytes == 0 or size_bytes <= self.max_dataset_bytes
        )

    def allows_monthly_runs(self, used: int) -> bool:
        return used >= 0 and (
            self.monthly_research_runs == 0 or used < self.monthly_research_runs
        )

    def allows_concurrency(self, active: int) -> bool:
        return active >= 0 and (
            self.max_concurrent_runs == 0 or active < self.max_concurrent_runs
        )


@dataclass(frozen=True)
class ResearchJob:
    """Tenant-owned research execution record."""

    id: UUID
    workspace_id: UUID
    dataset_id: str
    workflow_id: str
    status: ResearchJobStatus
    created_by: UUID | None = None

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise ValueError("dataset_id must not be empty")
        if not self.workflow_id.strip():
            raise ValueError("workflow_id must not be empty")


DEFAULT_USAGE_POLICIES: dict[Plan, UsagePolicy] = {
    Plan.FREE: UsagePolicy(monthly_research_runs=5, max_dataset_bytes=50_000_000, max_concurrent_runs=1),
    Plan.PRO: UsagePolicy(monthly_research_runs=100, max_dataset_bytes=2_000_000_000, max_concurrent_runs=2),
    Plan.TEAM: UsagePolicy(monthly_research_runs=1_000, max_dataset_bytes=10_000_000_000, max_concurrent_runs=8),
    Plan.ENTERPRISE: UsagePolicy(monthly_research_runs=0, max_dataset_bytes=0, max_concurrent_runs=0),
}


__all__ = [
    "DEFAULT_USAGE_POLICIES",
    "Plan",
    "ResearchJob",
    "ResearchJobStatus",
    "TenantContext",
    "UsagePolicy",
]
