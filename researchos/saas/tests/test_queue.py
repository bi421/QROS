from uuid import uuid4

from researchos.saas.queue import InMemoryResearchJobQueue, SupabaseResearchJobQueue


class RpcResult:
    def __init__(self, data):
        self.data = data


class RpcCall:
    def __init__(self, result):
        self.result = result
        self.params = None

    def rpc(self, _name, params):
        self.params = params
        return self

    def execute(self):
        return RpcResult(self.result)


def test_in_memory_queue_retains_identifier_only_message() -> None:
    queue = InMemoryResearchJobQueue()
    workspace_id = uuid4()
    job_id = uuid4()

    message_id = queue.enqueue(workspace_id, job_id)

    assert message_id == 1
    assert queue.messages == [(1, workspace_id, job_id)]


def test_supabase_queue_calls_protected_enqueue_rpc() -> None:
    client = RpcCall(42)
    queue = SupabaseResearchJobQueue(client)
    workspace_id = uuid4()
    job_id = uuid4()

    assert queue.enqueue(workspace_id, job_id, request_id="req-42") == 42
    assert client.params == {
        "p_research_run_id": str(job_id),
        "p_workspace_id": str(workspace_id),
        "p_request_id": "req-42",
    }
