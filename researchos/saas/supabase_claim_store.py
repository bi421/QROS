"""Supabase-backed tenant-scoped persistence for Research Claims."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from researchos.claims.claim import ResearchClaim


class SupabaseResearchClaimStore:
    """Persist ResearchClaim objects in the tenant-scoped SaaS database.

    RLS remains the authorization boundary. The adapter still requires an
    explicit workspace id and rejects cross-tenant claim objects before the
    request reaches Supabase.
    """

    def __init__(self, supabase_client: Any) -> None:
        self._client = supabase_client

    @staticmethod
    def _claim(row: dict[str, Any]) -> ResearchClaim:
        payload = row.get("payload")
        if not isinstance(payload, dict):
            raise RuntimeError("research claim payload is missing or invalid")
        claim = ResearchClaim.from_dict(payload)
        if claim.id != str(row["id"]):
            raise RuntimeError("research claim id does not match payload")
        if claim.workspace_id != str(row["workspace_id"]):
            raise RuntimeError("research claim workspace does not match payload")
        if claim.claim_hash != str(row["claim_hash"]):
            raise RuntimeError("research claim hash does not match payload")
        return claim

    @staticmethod
    def _row(claim: ResearchClaim, workspace_id: UUID) -> dict[str, Any]:
        if claim.workspace_id != str(workspace_id):
            raise ValueError("research claim workspace does not match tenant")
        return {
            "id": claim.id,
            "workspace_id": str(workspace_id),
            "statement": claim.statement,
            "claim_type": claim.claim_type.value,
            "evidence_state": claim.evidence_state.value,
            "version": claim.version,
            "parent_claim_id": claim.parent_claim_id,
            "research_id": claim.research_id,
            "creator": claim.creator,
            "plan_hash": claim.plan_hash,
            "plan_locked_at": (
                claim.plan_locked_at.isoformat() if claim.plan_locked_at else None
            ),
            "claim_hash": claim.claim_hash,
            "payload": claim.to_dict(),
        }

    def save(self, workspace_id: UUID, claim: ResearchClaim) -> ResearchClaim:
        row = self._row(claim, workspace_id)
        result = (
            self._client.table("research_claim")
            .upsert(row, on_conflict="workspace_id,id")
            .select("id,workspace_id,claim_hash,payload")
            .execute()
        )
        rows = result.data or []
        if len(rows) != 1:
            raise RuntimeError("research claim persistence returned no unique row")
        return self._claim(rows[0])

    def get(self, workspace_id: UUID, claim_id: str) -> ResearchClaim | None:
        result = (
            self._client.table("research_claim")
            .select("id,workspace_id,claim_hash,payload")
            .eq("workspace_id", str(workspace_id))
            .eq("id", claim_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return self._claim(rows[0]) if rows else None

    def list(
        self,
        workspace_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ResearchClaim], int]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("invalid pagination")
        result = (
            self._client.table("research_claim")
            .select("id,workspace_id,claim_hash,payload", count="exact")
            .eq("workspace_id", str(workspace_id))
            .order("id")
            .range(offset, offset + limit - 1)
            .execute()
        )
        return [self._claim(row) for row in (result.data or [])], int(result.count or 0)


__all__ = ["SupabaseResearchClaimStore"]
