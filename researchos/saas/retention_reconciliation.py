"""Idempotency and reconciliation contracts for destructive retention operations.

Destructive deletion is a distributed boundary: the resource delete and the
completion audit are separate side effects. This module makes the required
operation state explicit and provides a test-only in-memory implementation.
Production deletion remains gated on an atomic durable implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class DeletionOperationState(StrEnum):
    APPROVED = "APPROVED"
    DELETE_ATTEMPTED = "DELETE_ATTEMPTED"
    COMPLETED = "COMPLETED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


_ALLOWED_TRANSITIONS: dict[DeletionOperationState, frozenset[DeletionOperationState]] = {
    DeletionOperationState.APPROVED: frozenset(
        {DeletionOperationState.DELETE_ATTEMPTED, DeletionOperationState.RECONCILIATION_REQUIRED}
    ),
    DeletionOperationState.DELETE_ATTEMPTED: frozenset(
        {DeletionOperationState.COMPLETED, DeletionOperationState.RECONCILIATION_REQUIRED}
    ),
    DeletionOperationState.COMPLETED: frozenset(),
    DeletionOperationState.RECONCILIATION_REQUIRED: frozenset(),
}


@dataclass(frozen=True)
class DeletionOperation:
    workspace_id: UUID
    operation_id: str
    resource_type: str
    resource_id: str
    state: DeletionOperationState

    def __post_init__(self) -> None:
        if not self.operation_id.strip():
            raise ValueError("operation_id must not be empty")
        if not self.resource_type.strip():
            raise ValueError("resource_type must not be empty")
        if not self.resource_id.strip():
            raise ValueError("resource_id must not be empty")

    def transition_to(self, state: DeletionOperationState) -> "DeletionOperation":
        if state is self.state:
            return self
        if state not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(
                f"invalid deletion operation transition: {self.state} -> {state}"
            )
        return DeletionOperation(
            workspace_id=self.workspace_id,
            operation_id=self.operation_id,
            resource_type=self.resource_type,
            resource_id=self.resource_id,
            state=state,
        )


class DeletionOperationStore(Protocol):
    """Durable store contract for idempotent deletion state."""

    def get(self, workspace_id: UUID, operation_id: str) -> DeletionOperation | None:
        ...

    def put(self, operation: DeletionOperation) -> None:
        ...

    def transition(
        self,
        workspace_id: UUID,
        operation_id: str,
        resource_type: str,
        resource_id: str,
        state: DeletionOperationState,
    ) -> DeletionOperation:
        ...


class InMemoryDeletionOperationStore:
    """Test/development-only operation store."""

    def __init__(self) -> None:
        self._operations: dict[tuple[UUID, str], DeletionOperation] = {}

    def get(self, workspace_id: UUID, operation_id: str) -> DeletionOperation | None:
        return self._operations.get((workspace_id, operation_id))

    def put(self, operation: DeletionOperation) -> None:
        self._operations[(operation.workspace_id, operation.operation_id)] = operation

    def transition(
        self,
        workspace_id: UUID,
        operation_id: str,
        resource_type: str,
        resource_id: str,
        state: DeletionOperationState,
    ) -> DeletionOperation:
        current = self.get(workspace_id, operation_id)
        if current is None:
            raise KeyError("retention operation not found")
        if current.resource_type != resource_type or current.resource_id != resource_id:
            raise ValueError("retention operation resource identity mismatch")
        updated = current.transition_to(state)
        self.put(updated)
        return updated


def require_reconciliation_after_delete(
    *,
    store: DeletionOperationStore,
    workspace_id: UUID,
    operation_id: str,
    resource_type: str,
    resource_id: str,
) -> DeletionOperation:
    return store.transition(
        workspace_id,
        operation_id,
        resource_type,
        resource_id,
        DeletionOperationState.RECONCILIATION_REQUIRED,
    )


@dataclass(frozen=True)
class SupabaseDeletionOperationStore:
    """Server-side Supabase adapter for durable deletion-operation state."""

    supabase_client: object

    def get(self, workspace_id: UUID, operation_id: str) -> DeletionOperation | None:
        result = (
            self.supabase_client.table("retention_deletion_operation")
            .select("workspace_id,operation_id,resource_type,resource_id,state")
            .eq("workspace_id", str(workspace_id))
            .eq("operation_id", operation_id)
            .maybe_single()
            .execute()
        )
        data = result.data
        if data is None:
            return None
        return _operation_from_row(data)

    def put(self, operation: DeletionOperation) -> None:
        (
            self.supabase_client.table("retention_deletion_operation")
            .update({"state": operation.state.value})
            .eq("workspace_id", str(operation.workspace_id))
            .eq("operation_id", operation.operation_id)
            .eq("resource_type", operation.resource_type)
            .eq("resource_id", operation.resource_id)
            .execute()
        )

    def transition(
        self,
        workspace_id: UUID,
        operation_id: str,
        resource_type: str,
        resource_id: str,
        state: DeletionOperationState,
    ) -> DeletionOperation:
        result = self.supabase_client.rpc(
            "transition_retention_deletion_operation",
            {
                "p_workspace_id": str(workspace_id),
                "p_operation_id": operation_id,
                "p_resource_type": resource_type,
                "p_resource_id": resource_id,
                "p_state": state.value,
            },
        ).execute()
        data = result.data
        if isinstance(data, list):
            if len(data) != 1:
                raise RuntimeError("retention transition RPC returned no unique operation")
            data = data[0]
        if not isinstance(data, dict):
            raise RuntimeError("retention transition RPC returned invalid operation")
        return _operation_from_row(data)

    def reserve(
        self,
        workspace_id: UUID,
        operation_id: str,
        resource_type: str,
        resource_id: str,
    ) -> DeletionOperation:
        result = self.supabase_client.rpc(
            "reserve_retention_deletion_operation",
            {
                "p_workspace_id": str(workspace_id),
                "p_operation_id": operation_id,
                "p_resource_type": resource_type,
                "p_resource_id": resource_id,
            },
        ).execute()
        data = result.data
        if isinstance(data, list):
            if len(data) != 1:
                raise RuntimeError("retention reservation RPC returned no unique operation")
            data = data[0]
        if not isinstance(data, dict):
            raise RuntimeError("retention reservation RPC returned invalid operation")
        return _operation_from_row(data)


def _operation_from_row(data: object) -> DeletionOperation:
    if not isinstance(data, dict):
        raise RuntimeError("retention operation row is invalid")
    try:
        return DeletionOperation(
            workspace_id=UUID(str(data["workspace_id"])),
            operation_id=str(data["operation_id"]),
            resource_type=str(data["resource_type"]),
            resource_id=str(data["resource_id"]),
            state=DeletionOperationState(str(data["state"])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("retention operation row is malformed") from exc


__all__ = [
    "DeletionOperation",
    "DeletionOperationState",
    "DeletionOperationStore",
    "InMemoryDeletionOperationStore",
    "SupabaseDeletionOperationStore",
    "require_reconciliation_after_delete",
]
