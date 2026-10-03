from uuid import UUID, uuid4

from researchos.saas.finding import ResearchFindingRecord, VALIDATED_STATUS
from researchos.saas.supabase_finding_store import SupabaseResearchFindingStore


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
                return _Response([{"record": self.row}])

        return Call()

    def table(self, _name):
        return _Query(self.row)


def _record() -> ResearchFindingRecord:
    payload = {"finding": "validated", "metrics": {"brier_improvement": 0.1}}
    return ResearchFindingRecord(
        id=uuid4(),
        workspace_id=uuid4(),
        research_run_id=uuid4(),
        validation_id=uuid4(),
        result_manifest_sha256="a" * 64,
        validation_sha256="b" * 64,
        claim_id="claim-1",
        plan_hash="c" * 64,
        finding_sha256=ResearchFindingRecord.compute_finding_sha256(payload),
        status=VALIDATED_STATUS,
        payload=payload,
    )


def _row(record: ResearchFindingRecord) -> dict[str, object]:
    return {
        "id": str(record.id),
        "workspace_id": str(record.workspace_id),
        "research_run_id": str(record.research_run_id),
        "validation_id": str(record.validation_id),
        "result_manifest_sha256": record.result_manifest_sha256,
        "validation_sha256": record.validation_sha256,
        "claim_id": record.claim_id,
        "plan_hash": record.plan_hash,
        "finding_sha256": record.finding_sha256,
        "status": record.status,
        "payload": dict(record.payload),
        "contract_version": record.contract_version,
    }


def test_create_uses_governed_service_role_rpc() -> None:
    record = _record()
    client = _Client(_row(record))
    persisted = SupabaseResearchFindingStore(client).create(record)
    assert persisted == record
    assert client.rpc_calls[0][0] == "create_research_finding"
    args = client.rpc_calls[0][1]
    assert args["p_workspace_id"] == str(record.workspace_id)
    assert args["p_research_run_id"] == str(record.research_run_id)
    assert args["p_validation_id"] == str(record.validation_id)
    assert args["p_finding_sha256"] == record.finding_sha256


def test_get_is_tenant_scoped() -> None:
    record = _record()
    client = _Client(_row(record))
    store = SupabaseResearchFindingStore(client)
    assert store.get(record.workspace_id, record.research_run_id) == record
    client.row = None
    assert store.get(UUID(int=0), record.research_run_id) is None
