from uuid import UUID, uuid4

from researchos.saas.supabase_validation_store import SupabaseResearchValidationStore
from researchos.saas.validation import ResearchValidationRecord


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, row):
        self._row = row

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return _Response([self._row] if self._row else [])


class _Client:
    def __init__(self, row=None):
        self.row = row
        self.rpc_calls = []

    def rpc(self, name, args):
        self.rpc_calls.append((name, args))

        class Call:
            def execute(inner):
                return _Response([{"record": self.row, "replayed": False}])

        return Call()

    def table(self, _name):
        return _Query(self.row)


def _record() -> ResearchValidationRecord:
    return ResearchValidationRecord(
        id=uuid4(),
        workspace_id=uuid4(),
        research_run_id=uuid4(),
        result_manifest_sha256="a" * 64,
        claim_id="claim-1",
        plan_hash="b" * 64,
        validation_sha256="c" * 64,
        status="validated",
        metrics={"brier_improvement": 0.1},
    )


def _row(record: ResearchValidationRecord) -> dict[str, object]:
    return {
        "id": str(record.id),
        "workspace_id": str(record.workspace_id),
        "research_run_id": str(record.research_run_id),
        "result_manifest_sha256": record.result_manifest_sha256,
        "claim_id": record.claim_id,
        "plan_hash": record.plan_hash,
        "validation_sha256": record.validation_sha256,
        "status": record.status,
        "metrics": record.metrics,
        "contract_version": record.contract_version,
    }


def test_create_uses_governed_service_role_rpc() -> None:
    record = _record()
    client = _Client(_row(record))
    persisted = SupabaseResearchValidationStore(client).create(record)
    assert persisted == record
    assert client.rpc_calls[0][0] == "create_research_validation"
    assert client.rpc_calls[0][1]["p_workspace_id"] == str(record.workspace_id)


def test_get_is_tenant_scoped() -> None:
    record = _record()
    client = _Client(_row(record))
    store = SupabaseResearchValidationStore(client)
    assert store.get(record.workspace_id, record.research_run_id) == record
    client.row = None
    assert store.get(UUID(int=0), record.research_run_id) is None
