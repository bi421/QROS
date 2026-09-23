"""Supabase-backed durable persistence for governed research validation."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from researchos.saas.validation import ResearchValidationRecord
from researchos.saas.validation_api import ResearchValidationStore


class SupabaseResearchValidationStore(ResearchValidationStore):
    """Persist validation records through a service-role-only governed RPC."""

    def __init__(self, supabase_client: Any) -> None:
        self._client = supabase_client

    @staticmethod
    def _record(row: dict[str, Any]) -> ResearchValidationRecord:
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            raise RuntimeError("research validation metrics are invalid")
        return ResearchValidationRecord(
            id=UUID(str(row["id"])),
            workspace_id=UUID(str(row["workspace_id"])),
            research_run_id=UUID(str(row["research_run_id"])),
            result_manifest_sha256=str(row["result_manifest_sha256"]),
            claim_id=str(row["claim_id"]) if row.get("claim_id") else None,
            plan_hash=str(row["plan_hash"]) if row.get("plan_hash") else None,
            validation_sha256=str(row["validation_sha256"]),
            status=str(row["status"]),
            metrics={str(key): float(value) for key, value in metrics.items()},
            contract_version=str(row.get("contract_version", "1.0.0")),
        )

    def create(self, record: ResearchValidationRecord) -> ResearchValidationRecord:
        response = self._client.rpc(
            "create_research_validation",
            {
                "p_id": str(record.id),
                "p_workspace_id": str(record.workspace_id),
                "p_research_run_id": str(record.research_run_id),
                "p_result_manifest_sha256": record.result_manifest_sha256,
                "p_claim_id": record.claim_id,
                "p_plan_hash": record.plan_hash,
                "p_validation_sha256": record.validation_sha256,
                "p_status": record.status,
                "p_metrics": dict(record.metrics),
                "p_contract_version": record.contract_version,
            },
        ).execute()
        rows = response.data or []
        if len(rows) != 1:
            raise RuntimeError("research validation persistence returned no unique row")
        row = rows[0]
        return self._record(row.get("record", row))

    def get(self, workspace_id: UUID, research_run_id: UUID) -> ResearchValidationRecord | None:
        response = (
            self._client.table("research_validation")
            .select(
                "id,workspace_id,research_run_id,result_manifest_sha256,"
                "claim_id,plan_hash,validation_sha256,status,metrics,contract_version"
            )
            .eq("workspace_id", str(workspace_id)).is_("deleted_at", "null")
            .eq("research_run_id", str(research_run_id))
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return self._record(rows[0]) if rows else None
