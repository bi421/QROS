"""Application contracts for a multi-tenant QROS SaaS.

No scientific calculation belongs here. These contracts make the product
boundary explicit and give API, workers, and persistence layers one stable
vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from researchos.research_core.contracts import _validate_sha256


class Plan(str, Enum):
    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"


@dataclass(frozen=True)
class PageRequest:
    """Bounded offset pagination with explicit deterministic sorting."""
    limit: int = 50
    offset: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if self.offset < 0:
            raise ValueError("offset must not be negative")


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
    """Tenant-owned research execution record bound to an immutable dataset version."""

    id: UUID
    workspace_id: UUID
    dataset_version_id: UUID
    workflow_id: str
    status: ResearchJobStatus
    source_dataset_sha256: str
    created_by: UUID | None = None
    attempt_count: int = 0
    max_attempts: int = 3
    error_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_dataset_sha256", _validate_sha256(self.source_dataset_sha256, "source_dataset_sha256"))
        if not isinstance(self.dataset_version_id, UUID):
            raise TypeError("dataset_version_id must be a UUID")
        if not self.workflow_id.strip():
            raise ValueError("workflow_id must not be empty")
        if self.attempt_count < 0:
            raise ValueError("attempt_count must not be negative")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.attempt_count > self.max_attempts:
            raise ValueError("attempt_count cannot exceed max_attempts")


DEFAULT_USAGE_POLICIES: dict[Plan, UsagePolicy] = {
    Plan.FREE: UsagePolicy(monthly_research_runs=5, max_dataset_bytes=50_000_000, max_concurrent_runs=1),
    Plan.PRO: UsagePolicy(monthly_research_runs=100, max_dataset_bytes=2_000_000_000, max_concurrent_runs=2),
    Plan.TEAM: UsagePolicy(monthly_research_runs=1_000, max_dataset_bytes=10_000_000_000, max_concurrent_runs=8),
    Plan.ENTERPRISE: UsagePolicy(monthly_research_runs=0, max_dataset_bytes=0, max_concurrent_runs=0),
}


__all__ = [
    "DEFAULT_USAGE_POLICIES",
    "PageRequest",
    "Plan",
    "ResearchJob",
    "ResearchJobStatus",
    "TenantContext",
    "UsagePolicy",
]
