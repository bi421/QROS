from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from researchos.claims.claim import ResearchClaim, ResearchClaimType
from researchos.saas.supabase_claim_store import SupabaseResearchClaimStore


class _Response:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, rows):
        self._rows = rows
        self._filters = []
        self._range = None

    def upsert(self, row, on_conflict=None):
        self._rows[:] = [row]
        return self

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self._filters.append((column, str(value)))
        return self

    def order(self, *_args):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def limit(self, limit):
        self._range = (0, limit - 1)
        return self

    def execute(self):
        rows = [row for row in self._rows if all(str(row.get(column)) == value for column, value in self._filters)]
        if self._range is not None:
            start, end = self._range
            rows = rows[start:end + 1]
        return _Response(rows, len(rows))


class _Client:
    def __init__(self):
        self.rows = []
        self.last_table = None

    def table(self, name):
        self.last_table = name
        return _Query(self.rows)


def _claim(workspace_id: UUID) -> ResearchClaim:
    return ResearchClaim(
        statement="A testable tenant-scoped research claim",
        claim_type=ResearchClaimType.EMPIRICAL,
        target_population="test",
        instrument="XAUUSD",
        horizon="60m",
        creator="user-1",
        workspace_id=str(workspace_id),
    )


def test_save_and_get_round_trip_preserves_claim_identity() -> None:
    workspace_id = uuid4()
    client = _Client()
    store = SupabaseResearchClaimStore(client)
    claim = _claim(workspace_id)

    saved = store.save(workspace_id, claim)
    loaded = store.get(workspace_id, claim.id)

    assert client.last_table == "research_claim"
    assert saved.id == claim.id
    assert loaded is not None
    assert loaded.claim_hash == claim.claim_hash
    assert loaded.workspace_id == str(workspace_id)


def test_save_rejects_cross_tenant_claim_before_database_write() -> None:
    workspace_id = uuid4()
    other_workspace_id = uuid4()
    client = _Client()
    store = SupabaseResearchClaimStore(client)
    claim = _claim(other_workspace_id)

    with pytest.raises(ValueError, match="workspace"):
        store.save(workspace_id, claim)
    assert client.rows == []


def test_get_is_tenant_scoped() -> None:
    workspace_id = uuid4()
    other_workspace_id = uuid4()
    client = _Client()
    store = SupabaseResearchClaimStore(client)
    claim = _claim(workspace_id)
    store.save(workspace_id, claim)

    assert store.get(other_workspace_id, claim.id) is None


def test_list_requires_bounded_pagination() -> None:
    store = SupabaseResearchClaimStore(_Client())
    with pytest.raises(ValueError, match="pagination"):
        store.list(uuid4(), limit=101)
