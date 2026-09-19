from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from researchos.claims.claim import ResearchClaim
from researchos.saas.api import create_app
from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole


class StaticAuth:
    def __init__(self, context: TenantContext) -> None:
        self.context = context

    def authenticate(
        self,
        authorization: str | None,
        requested_workspace_id: UUID | None = None,
    ) -> TenantContext:
        if authorization != "Bearer test":
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="invalid credentials")
        if requested_workspace_id is not None and requested_workspace_id != self.context.workspace_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="workspace is not authorized")
        return self.context


class FakeClaimStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, str], ResearchClaim] = {}
        self.save_calls = 0

    def save(self, workspace_id: UUID, claim: ResearchClaim) -> ResearchClaim:
        if claim.workspace_id != str(workspace_id):
            raise ValueError("research claim workspace does not match tenant")
        self.save_calls += 1
        self.rows[(workspace_id, claim.id)] = claim
        return claim

    def get(self, workspace_id: UUID, claim_id: str) -> ResearchClaim | None:
        return self.rows.get((workspace_id, claim_id))

    def list(
        self, workspace_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> tuple[list[ResearchClaim], int]:
        values = sorted(
            (
                claim
                for (row_workspace, _), claim in self.rows.items()
                if row_workspace == workspace_id
            ),
            key=lambda claim: claim.id,
        )
        return values[offset : offset + limit], len(values)


def _client(
    *,
    context: TenantContext | None = None,
    store: FakeClaimStore | None = None,
) -> tuple[TestClient, TenantContext, FakeClaimStore]:
    context = context or TenantContext(
        user_id=uuid4(),
        workspace_id=uuid4(),
        plan=Plan.PRO,
        role=WorkspaceRole.RESEARCHER,
    )
    store = store or FakeClaimStore()
    client = TestClient(
        create_app(
            auth_provider=StaticAuth(context),
            claim_store=store,
        )
    )
    return client, context, store


def _payload(statement: str) -> dict[str, object]:
    return {
        "statement": statement,
        "claim_type": "empirical",
        "target_population": "XAUUSD M1 2021-2025",
        "instrument": "XAUUSD",
        "horizon": "60m",
        "timestamp_policy": "event-time only",
        "economic_rationale": "test",
        "falsification_conditions": ["mean return <= 0"],
        "primary_metrics": ["mean_return"],
        "minimum_evidence_requirements": ["N >= 100"],
        "research_id": "research-1",
        "ontology_tags": ["macro"],
    }


def test_create_get_and_list_research_claim_is_tenant_scoped() -> None:
    client, context, store = _client()
    created = client.post(
        "/v1/research-claims",
        headers={"Authorization": "Bearer test"},
        json=_payload("DXY shocks are associated with XAUUSD returns."),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["workspace_id"] == str(context.workspace_id)
    assert body["evidence_state"] == "UNTESTED"
    assert body["version"] == 1
    assert body["creator"] == str(context.user_id)
    assert len(body["claim_hash"]) == 64

    fetched = client.get(
        f"/v1/research-claims/{body['id']}",
        headers={"Authorization": "Bearer test"},
    )
    assert fetched.status_code == 200
    assert fetched.json() == body

    listed = client.get(
        "/v1/research-claims?limit=10&offset=0",
        headers={"Authorization": "Bearer test"},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"] == [body]
    assert store.save_calls == 1


def test_identical_claim_create_is_naturally_idempotent() -> None:
    client, _, store = _client()
    payload = _payload("Same statement")
    first = client.post(
        "/v1/research-claims",
        headers={"Authorization": "Bearer test"},
        json=payload,
    )
    second = client.post(
        "/v1/research-claims",
        headers={"Authorization": "Bearer test"},
        json=payload,
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["claim_hash"] == second.json()["claim_hash"]
    assert store.save_calls == 2


def test_cross_tenant_claim_lookup_is_not_visible() -> None:
    owner = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    other = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    store = FakeClaimStore()
    owner_client, _, _ = _client(context=owner, store=store)
    other_client, _, _ = _client(context=other, store=store)

    created = owner_client.post(
        "/v1/research-claims",
        headers={"Authorization": "Bearer test"},
        json=_payload("Tenant A claim"),
    )
    claim_id = created.json()["id"]

    assert other_client.get(
        f"/v1/research-claims/{claim_id}",
        headers={"Authorization": "Bearer test"},
    ).status_code == 404
    assert other_client.get(
        "/v1/research-claims",
        headers={"Authorization": "Bearer test"},
    ).json()["total"] == 0


def test_viewer_cannot_create_claim_but_can_read() -> None:
    client, _, _ = _client(
        context=TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.VIEWER)
    )
    response = client.post(
        "/v1/research-claims",
        headers={"Authorization": "Bearer test"},
        json=_payload("Viewer cannot create"),
    )
    assert response.status_code == 403


def test_unconfigured_claim_persistence_fails_closed() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)
    client = TestClient(create_app(auth_provider=StaticAuth(context)))
    response = client.get(
        "/v1/research-claims",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 503


def test_claim_pagination_is_bounded() -> None:
    client, _, _ = _client()
    assert client.get(
        "/v1/research-claims?limit=101",
        headers={"Authorization": "Bearer test"},
    ).status_code == 422
    assert client.get(
        "/v1/research-claims?offset=-1",
        headers={"Authorization": "Bearer test"},
    ).status_code == 422
