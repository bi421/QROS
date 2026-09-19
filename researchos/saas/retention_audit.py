"""Tenant-scoped audit integration helpers."""

from __future__ import annotations

from typing import Callable
from uuid import UUID

from researchos.saas.audit import AuditEvent, AuditEventStore
from researchos.saas.retention import DeletionCandidate


def retention_audit_callback(
    store: AuditEventStore,
    *,
    workspace_id: UUID,
    actor_user_id: UUID | None = None,
    request_id: str | None = None,
) -> Callable[[DeletionCandidate, str], None]:
    """Create a durable audit callback for retention execution.

    The workspace is supplied by the already-authorized tenant context rather
    than inferred from the deletion candidate. This prevents resource IDs from
    becoming an implicit tenant selector.
    """

    def audit(candidate: DeletionCandidate, action: str) -> None:
        store.append(
            AuditEvent.create(
                workspace_id=workspace_id,
                action=action,
                resource_type=candidate.resource_type,
                resource_id=candidate.resource_id,
                actor_user_id=actor_user_id,
                request_id=request_id,
                metadata={
                    "reference_count": candidate.reference_count,
                    "legal_hold": candidate.legal_hold,
                },
            )
        )

    return audit


__all__ = ["retention_audit_callback"]
