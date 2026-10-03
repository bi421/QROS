"""Governed completion contract for durable retention reconciliation."""

from __future__ import annotations

from uuid import UUID

from researchos.saas.retention_reconciliation import (
    DeletionOperation,
    DeletionOperationState,
    DeletionOperationStore,
)


def complete_reconciliation(
    *,
    store: DeletionOperationStore,
    workspace_id: UUID,
    operation_id: str,
    resource_type: str,
    resource_id: str,
) -> DeletionOperation:
    """Record COMPLETED only from an existing RECONCILIATION_REQUIRED operation.

    The caller must verify independently that the resource is absent before
    invoking this function. This function performs no destructive side effect.
    """
    return store.transition(
        workspace_id,
        operation_id,
        resource_type,
        resource_id,
        DeletionOperationState.COMPLETED,
    )


__all__ = ["complete_reconciliation"]
