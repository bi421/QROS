"""Durable research-job queue boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class ResearchQueueMessage:
    """One identifier-only message received from the governed research queue."""

    message_id: int
    workspace_id: UUID
    research_run_id: UUID


class ResearchJobQueue(Protocol):
    def enqueue(self, workspace_id: UUID, job_id: UUID, *, request_id: str | None = None) -> int:
        """Persist a queue message containing identifiers only and return its message id."""

    def receive(self) -> ResearchQueueMessage | None:
        """Receive one message using the queue's visibility semantics."""

    def ack(self, message_id: int) -> None:
        """Acknowledge one message only after its governed lifecycle is handled."""


class InMemoryResearchJobQueue:
    """Development/test queue; messages are retained for inspection."""

    def __init__(self) -> None:
        self.messages: list[tuple[int, UUID, UUID]] = []
        self._received: set[int] = set()

    def enqueue(self, workspace_id: UUID, job_id: UUID, *, request_id: str | None = None) -> int:
        message_id = len(self.messages) + 1
        self.messages.append((message_id, workspace_id, job_id))
        if request_id is not None:
            self.request_ids[job_id] = request_id
        return message_id

    def receive(self) -> ResearchQueueMessage | None:
        for message_id, workspace_id, job_id in self.messages:
            if message_id not in self._received:
                self._received.add(message_id)
                return ResearchQueueMessage(message_id, workspace_id, job_id)
        return None

    def ack(self, message_id: int) -> None:
        if message_id <= 0:
            raise ValueError("message_id must be positive")
        self.messages = [message for message in self.messages if message[0] != message_id]
        self._received.discard(message_id)


@dataclass(frozen=True)
class SupabaseResearchJobQueue:
    """Server-side Supabase adapter for protected enqueue/consume/ack RPCs."""

    supabase_client: object
    visibility_timeout_seconds: int = 1200

    def __post_init__(self) -> None:
        if not 1 <= self.visibility_timeout_seconds <= 86400:
            raise ValueError("visibility_timeout_seconds must be between 1 and 86400")

    def enqueue(self, workspace_id: UUID, job_id: UUID, *, request_id: str | None = None) -> int:
        result = self.supabase_client.rpc(
            "enqueue_research_run",
            {
                "p_research_run_id": str(job_id),
                "p_workspace_id": str(workspace_id),
                "p_request_id": request_id,
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

    def receive(self) -> ResearchQueueMessage | None:
        result = self.supabase_client.rpc(
            "receive_research_run",
            {"p_visibility_timeout": self.visibility_timeout_seconds},
        ).execute()
        rows = result.data or []
        if len(rows) > 1:
            raise RuntimeError("research queue receive RPC returned multiple messages")
        if not rows:
            return None
        row = rows[0]
        if not isinstance(row, dict):
            raise RuntimeError("research queue receive RPC returned invalid message")
        try:
            message_id = int(row["msg_id"])
            workspace_id = UUID(str(row["workspace_id"]))
            research_run_id = UUID(str(row["research_run_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("research queue message failed identifier validation") from exc
        if message_id <= 0:
            raise ValueError("research queue message id must be positive")
        return ResearchQueueMessage(message_id, workspace_id, research_run_id)

    def ack(self, message_id: int) -> None:
        if message_id <= 0:
            raise ValueError("message_id must be positive")
        result = self.supabase_client.rpc(
            "ack_research_run",
            {"p_message_id": message_id},
        ).execute()
        data = result.data
        if isinstance(data, list):
            if len(data) != 1:
                raise RuntimeError("research queue ack RPC returned no unique result")
            data = data[0]
        value = data.get("ack_research_run") if isinstance(data, dict) else data
        if value is not True:
            raise RuntimeError("research queue message was not acknowledged")


__all__ = [
    "InMemoryResearchJobQueue",
    "ResearchJobQueue",
    "ResearchQueueMessage",
    "SupabaseResearchJobQueue",
]
