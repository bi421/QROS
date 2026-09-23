"""Supabase-backed durable persistence for governed research findings."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from researchos.core.timestamp import utc_now

from researchos.saas.finding import ResearchFindingRecord
from researchos.saas.finding_api import ResearchFindingStore


class SupabaseResearchFindingStore(ResearchFindingStore):
    def __init__(self, supabase_client: Any) -> None:
        self._client = supabase_client

    @staticmethod
    def _record(row: dict[str, Any]) -> ResearchFindingRecord:
        payload = row.get("payload")
        if not isinstance(payload, dict):
            raise RuntimeError("research finding payload is invalid")
        return ResearchFindingRecord(
            id=UUID(str(row["id"])),
            workspace_id=UUID(str(row["workspace_id"])),
            research_run_id=UUID(str(row["research_run_id"])),
            validation_id=UUID(str(row["validation_id"])),
            result_manifest_sha256=str(row["result_manifest_sha256"]),
            validation_sha256=str(row["validation_sha256"]),
            claim_id=str(row["claim_id"]) if row.get("claim_id") else None,
            plan_hash=str(row["plan_hash"]) if row.get("plan_hash") else None,
            finding_sha256=str(row["finding_sha256"]),
            status=str(row["status"]),
            payload=payload,
            contract_version=str(row.get("contract_version", "1.0.0")),
            created_at=(
                datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
                if row.get("created_at")
                else utc_now()
            ),
        )

    def create(self, record: ResearchFindingRecord) -> ResearchFindingRecord:
        response = self._client.rpc(
            "create_research_finding",
            {
                "p_id": str(record.id),
                "p_workspace_id": str(record.workspace_id),
                "p_research_run_id": str(record.research_run_id),
                "p_validation_id": str(record.validation_id),
                "p_result_manifest_sha256": record.result_manifest_sha256,
                "p_validation_sha256": record.validation_sha256,
                "p_claim_id": record.claim_id,
                "p_plan_hash": record.plan_hash,
                "p_finding_sha256": record.finding_sha256,
                "p_status": record.status,
                "p_payload": dict(record.payload),
                "p_contract_version": record.contract_version,
            },
        ).execute()
        rows = response.data or []
        if len(rows) != 1:
            raise RuntimeError("research finding persistence returned no unique row")
        return self._record(rows[0].get("record", rows[0]))

    def list(
        self,
        workspace_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        status: str | None = None,
    ) -> tuple[list[ResearchFindingRecord], int]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("invalid pagination")
        if sort_by not in {"created_at", "status"}:
            raise ValueError("invalid sort field")
        if sort_order not in {"asc", "desc"}:
            raise ValueError("invalid sort order")
        query = (
            self._client.table("research_finding")
            .select(
                "id,workspace_id,research_run_id,validation_id,result_manifest_sha256,"
                "validation_sha256,claim_id,plan_hash,finding_sha256,status,payload,contract_version,created_at",
                count="exact",
            )
            .eq("workspace_id", str(workspace_id))
        )
        if status:
            query = query.eq("status", status)
        result = (
            query
            .order(sort_by, desc=sort_order == "desc")
            .range(offset, offset + limit - 1)
            .execute()
        )
        return [self._record(row) for row in (result.data or [])], int(result.count or 0)

    def get(self, workspace_id: UUID, research_run_id: UUID) -> ResearchFindingRecord | None:
        response = (
            self._client.table("research_finding")
            .select(
                "id,workspace_id,research_run_id,validation_id,result_manifest_sha256,"
                "validation_sha256,claim_id,plan_hash,finding_sha256,status,payload,contract_version"
            )
            .eq("workspace_id", str(workspace_id))
            .eq("research_run_id", str(research_run_id))
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return self._record(rows[0]) if rows else None
