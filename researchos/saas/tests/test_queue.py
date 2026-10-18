from uuid import uuid4

import pytest

from researchos.saas.queue import (
    InMemoryResearchJobQueue,
    ResearchQueueMessage,
    SupabaseResearchJobQueue,
)


class RpcResult:
    def __init__(self, data):
        self.data = data


class RpcCall:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.params = []

    def rpc(self, name, params):
        self.params.append((name, params))
        return self

    def execute(self):
        return RpcResult(next(self.responses))


def test_in_memory_queue_retains_identifier_only_message() -> None:
    queue = InMemoryResearchJobQueue()
    workspace_id = uuid4()
    job_id = uuid4()

    message_id = queue.enqueue(workspace_id, job_id)

    assert message_id == 1
    assert queue.messages == [(1, workspace_id, job_id)]
    assert queue.receive() == ResearchQueueMessage(1, workspace_id, job_id)


def test_in_memory_queue_ack_removes_message() -> None:
    queue = InMemoryResearchJobQueue()
    workspace_id = uuid4()
    job_id = uuid4()
    queue.enqueue(workspace_id, job_id)

    message = queue.receive()
    assert message is not None
    queue.ack(message.message_id)

    assert queue.messages == []
    assert queue.receive() is None


def test_in_memory_queue_preserves_request_id_through_receive_and_ack() -> None:
    queue = InMemoryResearchJobQueue()
    workspace_id = uuid4()
    job_id = uuid4()
    queue.enqueue(workspace_id, job_id, request_id="api-request-123")

    assert queue.receive() == ResearchQueueMessage(
        1, workspace_id, job_id, "api-request-123"
    )
    queue.ack(1)
    assert job_id not in queue.request_ids


def test_supabase_queue_calls_protected_enqueue_rpc() -> None:
    client = RpcCall([[42]])
    queue = SupabaseResearchJobQueue(client)
    workspace_id = uuid4()
    job_id = uuid4()

    assert queue.enqueue(workspace_id, job_id) == 42
    assert client.params == [(
        "enqueue_research_run",
        {"p_research_run_id": str(job_id), "p_workspace_id": str(workspace_id), "p_request_id": None},
    )]


def test_supabase_queue_receives_and_validates_identifier_message() -> None:
    workspace_id = uuid4()
    job_id = uuid4()
    client = RpcCall([[{
        "msg_id": 7,
        "workspace_id": str(workspace_id),
        "research_run_id": str(job_id),
        "request_id": "api-request-123",
    }]])
    queue = SupabaseResearchJobQueue(client)

    assert queue.receive() == ResearchQueueMessage(7, workspace_id, job_id, "api-request-123")
    assert client.params == [("receive_research_run", {"p_visibility_timeout": 1200})]


def test_supabase_queue_rejects_malformed_message() -> None:
    client = RpcCall([[{"msg_id": 7, "workspace_id": "not-a-uuid", "research_run_id": str(uuid4())}]])
    queue = SupabaseResearchJobQueue(client)

    with pytest.raises(ValueError, match="identifier validation"):
        queue.receive()


def test_supabase_queue_rejects_invalid_request_id() -> None:
    client = RpcCall([[{
        "msg_id": 7,
        "workspace_id": str(uuid4()),
        "research_run_id": str(uuid4()),
        "request_id": "r" * 129,
    }]])
    queue = SupabaseResearchJobQueue(client)

    with pytest.raises(ValueError, match="request_id"):
        queue.receive()


def test_supabase_queue_ack_requires_true_result() -> None:
    client = RpcCall([[True]])
    queue = SupabaseResearchJobQueue(client)

    queue.ack(7)
    assert client.params == [("ack_research_run", {"p_message_id": 7})]

    bad = SupabaseResearchJobQueue(RpcCall([[False]]))
    with pytest.raises(RuntimeError, match="not acknowledged"):
        bad.ack(7)
