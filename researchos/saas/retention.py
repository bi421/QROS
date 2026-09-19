"""Fail-closed retention and deletion policy contracts for SaaS data.

This module separates eligibility from the destructive delete operation.
A resource is never eligible merely because its age elapsed: active references
and legal holds must also be absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class RetentionDecision(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    RETAIN = "RETAIN"


@dataclass(frozen=True)
class DeletionCandidate:
    resource_type: str
    resource_id: str
    created_at: datetime
    reference_count: int = 0
    legal_hold: bool = False

    def __post_init__(self) -> None:
        if not self.resource_type.strip():
            raise ValueError("resource_type must not be empty")
        if not self.resource_id.strip():
            raise ValueError("resource_id must not be empty")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.reference_count < 0:
            raise ValueError("reference_count must be non-negative")


@dataclass(frozen=True)
class RetentionPolicy:
    min_age: timedelta = timedelta(days=30)
    deletable_resource_types: frozenset[str] = frozenset(
        {"dataset", "dataset_version", "artifact"}
    )

    def __post_init__(self) -> None:
        if self.min_age < timedelta(0):
            raise ValueError("min_age must be non-negative")
        if not self.deletable_resource_types:
            raise ValueError("at least one deletable resource type is required")

    def evaluate(
        self,
        candidate: DeletionCandidate,
        *,
        now: datetime,
    ) -> tuple[RetentionDecision, str]:
        """Return a deterministic fail-closed deletion decision."""
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if candidate.resource_type not in self.deletable_resource_types:
            return RetentionDecision.RETAIN, "resource_type_not_deletable"
        if candidate.legal_hold:
            return RetentionDecision.RETAIN, "legal_hold"
        if candidate.reference_count != 0:
            return RetentionDecision.RETAIN, "active_references"
        if candidate.created_at + self.min_age > now:
            return RetentionDecision.RETAIN, "retention_window_active"
        return RetentionDecision.ELIGIBLE, "retention_window_elapsed"


def evaluate_deletion(
    candidate: DeletionCandidate,
    *,
    now: datetime,
    policy: RetentionPolicy | None = None,
) -> tuple[RetentionDecision, str]:
    """Evaluate one candidate using the default retention policy."""
    return (policy or RetentionPolicy()).evaluate(candidate, now=now)


__all__ = [
    "DeletionCandidate",
    "RetentionDecision",
    "RetentionPolicy",
    "evaluate_deletion",
]
