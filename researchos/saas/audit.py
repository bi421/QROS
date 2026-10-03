"""Tenant-scoped immutable audit-event contracts for SaaS security actions.

The audit layer is deliberately provider-neutral. Production persistence is
append-only and server-side; callers must never put secrets or raw tokens in
metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4


@dataclass(frozen=True)
class AuditEvent:
    id: UUID
    workspace_id: UUID
    action: str
    resource_type: str
    resource_id: str | None
    actor_user_id: UUID | None
    request_id: str | None
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        workspace_id: UUID,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        actor_user_id: UUID | None = None,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "AuditEvent":
        return cls(
            id=uuid4(),
            workspace_id=workspace_id,
            action=action.strip(),
            resource_type=resource_type.strip(),
            resource_id=resource_id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            metadata=dict(metadata or {}),
            created_at=datetime.now(timezone.utc),
        )

    def __post_init__(self) -> None:
        if not self.action:
            raise ValueError("action must not be empty")
        if not self.resource_type:
            raise ValueError("resource_type must not be empty")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if len(self.action) > 128:
            raise ValueError("action exceeds maximum length")
        if len(self.resource_type) > 128:
            raise ValueError("resource_type exceeds maximum length")
        if self.resource_id is not None and len(self.resource_id) > 256:
            raise ValueError("resource_id exceeds maximum length")
        if self.request_id is not None and len(self.request_id) > 128:
            raise ValueError("request_id exceeds maximum length")


class AuditEventStore(Protocol):
    def append(self, event: AuditEvent) -> None:
        """Persist one immutable audit event."""


class InMemoryAuditEventStore:
    """Test/development-only append-only audit event store."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self._events.append(event)

    def list(self, workspace_id: UUID) -> list[AuditEvent]:
        return [event for event in self._events if event.workspace_id == workspace_id]


class SupabaseAuditEventStore:
    """Server-side tenant-scoped append-only audit event persistence."""

    def __init__(self, supabase_client: Any) -> None:
        self._client = supabase_client

    def append(self, event: AuditEvent) -> None:
        self._client.table("audit_event").insert(
            {
                "id": str(event.id),
                "workspace_id": str(event.workspace_id),
                "action": event.action,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
                "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
                "request_id": event.request_id,
                "metadata": event.metadata,
                "created_at": event.created_at.isoformat(),
            }
        ).execute()


__all__ = [
    "AuditEvent",
    "AuditEventStore",
    "InMemoryAuditEventStore",
    "SupabaseAuditEventStore",
]
