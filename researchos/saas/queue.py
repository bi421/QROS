"""Durable research-job queue boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class ResearchJobQueue(Protocol):
    def enqueue(self, workspace_id: UUID, job_id: UUID) -> int:
        """Persist a queue message containing identifiers only and return its message id."""


class InMemoryResearchJobQueue:
    """Development/test queue; messages are retained for inspection."""

    def __init__(self) -> None:
        self.messages: list[tuple[int, UUID, UUID]] = []

    def enqueue(self, workspace_id: UUID, job_id: UUID) -> int:
        message_id = len(self.messages) + 1
        self.messages.append((message_id, workspace_id, job_id))
        return message_id


@dataclass(frozen=True)
class SupabaseResearchJobQueue:
    """Server-side Supabase adapter for the protected enqueue RPC."""

    supabase_client: object

    def enqueue(self, workspace_id: UUID, job_id: UUID) -> int:
        result = self.supabase_client.rpc(
            "enqueue_research_run",
            {
                "p_research_run_id": str(job_id),
                "p_workspace_id": str(workspace_id),
            },
        ).execute()
        data = result.data
        if isinstance(data, list):
            if len(data) != 1:
                raise RuntimeError("research queue RPC returned no unique message id")
            data = data[0]
        if isinstance(data, dict):
            value = data.get("enqueue_research_run")
        else:
            value = data
        if value is None:
            raise RuntimeError("research queue RPC returned no message id")
        return int(value)


__all__ = ["InMemoryResearchJobQueue", "ResearchJobQueue", "SupabaseResearchJobQueue"]
