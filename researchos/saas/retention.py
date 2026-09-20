"""Fail-closed retention and deletion policy contracts for SaaS data.

This module separates eligibility from the destructive delete operation.
A resource is never eligible merely because its age elapsed: active references
and legal holds must also be absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any


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


@dataclass(frozen=True)
class DeletionExecution:
    """Auditable result of a retention deletion attempt."""

    decision: RetentionDecision
    reason: str
    deleted: bool


def execute_deletion(
    candidate: DeletionCandidate,
    *,
    now: datetime,
    policy: RetentionPolicy | None = None,
    approved: bool = False,
    destructive_deletion_enabled: bool = False,
    audit: Any | None = None,
    delete: Any | None = None,
    dependency_check: Any | None = None,
    authorize: Any | None = None,
    operation_store: Any | None = None,
    workspace_id: Any | None = None,
    operation_id: str | None = None,
) -> DeletionExecution:
    """Execute deletion only after eligibility, approval, and audit gates pass.

    The executor is deliberately fail-closed: approval, tenant authorization,
    dependency resolution, audit sink, and delete operation are all required
    before an eligible resource can be destroyed.
    The audit callback is invoked before deletion; if it raises, deletion does
    not occur. Destructive execution also requires a durable operation store and
    transitions APPROVED -> DELETE_ATTEMPTED before the delete. Any delete or
    post-delete-audit failure enters RECONCILIATION_REQUIRED. No recovery or
    retry is performed implicitly.
    """
    decision, reason = evaluate_deletion(candidate, now=now, policy=policy)
    if decision is not RetentionDecision.ELIGIBLE:
        return DeletionExecution(decision, reason, False)
    if not destructive_deletion_enabled:
        return DeletionExecution(
            RetentionDecision.RETAIN, "production_destructive_deletion_disabled", False
        )
    if not approved:
        return DeletionExecution(RetentionDecision.RETAIN, "approval_required", False)
    if authorize is None:
        return DeletionExecution(
            RetentionDecision.RETAIN, "tenant_authorization_required", False
        )
    if not authorize(candidate):
        return DeletionExecution(
            RetentionDecision.RETAIN, "tenant_authorization_denied", False
        )
    if dependency_check is None:
        return DeletionExecution(
            RetentionDecision.RETAIN, "dependency_check_required", False
        )
    if not dependency_check(candidate):
        return DeletionExecution(RetentionDecision.RETAIN, "active_dependencies", False)
    if audit is None:
        return DeletionExecution(RetentionDecision.RETAIN, "audit_sink_required", False)
    if delete is None:
        return DeletionExecution(RetentionDecision.RETAIN, "delete_operation_required", False)
    if operation_store is None or workspace_id is None or operation_id is None:
        return DeletionExecution(
            RetentionDecision.RETAIN, "durable_operation_required", False
        )

    audit(candidate, "deletion_approved")
    operation_store.transition(
        workspace_id,
        operation_id,
        candidate.resource_type,
        candidate.resource_id,
        "DELETE_ATTEMPTED",
    )
    try:
        delete(candidate)
    except Exception:
        operation_store.transition(
            workspace_id,
            operation_id,
            candidate.resource_type,
            candidate.resource_id,
            "RECONCILIATION_REQUIRED",
        )
        raise

    try:
        audit(candidate, "deletion_completed")
    except Exception:
        operation_store.transition(
            workspace_id,
            operation_id,
            candidate.resource_type,
            candidate.resource_id,
            "RECONCILIATION_REQUIRED",
        )
        return DeletionExecution(
            RetentionDecision.ELIGIBLE, "reconciliation_required", True
        )

    operation_store.transition(
        workspace_id,
        operation_id,
        candidate.resource_type,
        candidate.resource_id,
        "COMPLETED",
    )
    return DeletionExecution(RetentionDecision.ELIGIBLE, "deletion_completed", True)


__all__ = [
    "DeletionCandidate",
    "RetentionDecision",
    "RetentionPolicy",
    "evaluate_deletion",
    "DeletionExecution",
    "execute_deletion",
]
