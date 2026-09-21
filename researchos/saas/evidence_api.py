"""Tenant-scoped Evidence read API for the QROS Golden Path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel

from researchos.saas.contracts import TenantContext


@dataclass(frozen=True)
class ResearchEvidenceRecord:
    id: UUID
    workspace_id: UUID
    research_run_id: UUID
    claim_id: UUID | None
    plan_hash: str | None
    artifact_id: UUID | None
    claim: str
    status: str
    provenance: dict[str, object]


class ResearchEvidenceStore(Protocol):
    def list_for_run(self, workspace_id: UUID, research_run_id: UUID) -> list[ResearchEvidenceRecord]:
        ...


class InMemoryResearchEvidenceStore:
    def __init__(self) -> None:
        self._rows: dict[UUID, ResearchEvidenceRecord] = {}

    def add(self, record: ResearchEvidenceRecord) -> ResearchEvidenceRecord:
        if record.workspace_id is None:
            raise ValueError("evidence workspace is required")
        self._rows[record.id] = record
        return record

    def list_for_run(self, workspace_id: UUID, research_run_id: UUID) -> list[ResearchEvidenceRecord]:
        return sorted(
            (
                row
                for row in self._rows.values()
                if row.workspace_id == workspace_id and row.research_run_id == research_run_id
            ),
            key=lambda row: str(row.id),
        )


class SupabaseResearchEvidenceStore:
    """Read-only customer adapter; evidence writes remain worker/governance-owned."""

    def __init__(self, supabase_client: Any) -> None:
        self._client = supabase_client

    @staticmethod
    def _record(row: dict[str, Any]) -> ResearchEvidenceRecord:
        artifact = row.get("artifact_id")
        provenance = row.get("provenance")
        if not isinstance(provenance, dict):
            raise RuntimeError("evidence provenance is invalid")
        return ResearchEvidenceRecord(
            id=UUID(str(row["id"])),
            workspace_id=UUID(str(row["workspace_id"])),
            research_run_id=UUID(str(row["research_run_id"])),
            claim_id=UUID(str(row["claim_id"])) if row.get("claim_id") else None,
            plan_hash=str(row["plan_hash"]) if row.get("plan_hash") else None,
            artifact_id=UUID(str(artifact)) if artifact else None,
            claim=str(row["claim"]),
            status=str(row["status"]),
            provenance=dict(provenance),
        )

    def list_for_run(self, workspace_id: UUID, research_run_id: UUID) -> list[ResearchEvidenceRecord]:
        run = (
            self._client.table("research_run")
            .select("id,claim_id,plan_hash")
            .eq("id", str(research_run_id))
            .eq("workspace_id", str(workspace_id))
            .limit(1)
            .execute()
        )
        if not (run.data or []):
            return []
        result = (
            self._client.table("evidence")
            .select("id,workspace_id,research_run_id,artifact_id,claim,status,provenance")
            .eq("workspace_id", str(workspace_id))
            .eq("research_run_id", str(research_run_id))
            .order("id")
            .execute()
        )
        records = []
        for row in (result.data or []):
            row["claim_id"] = run.data[0].get("claim_id")
            row["plan_hash"] = run.data[0].get("plan_hash")
            records.append(self._record(row))
        return records


class ResearchEvidenceResponse(BaseModel):
    id: str
    workspace_id: str
    research_run_id: str
    claim_id: str | None
    plan_hash: str | None
    artifact_id: str | None
    claim: str
    status: str
    provenance: dict[str, object]


def register_research_evidence_routes(
    router: Any,
    *,
    tenant_dependency: Any,
    evidence_store: ResearchEvidenceStore | None,
) -> None:
    @router.get(
        "/v1/research-runs/{research_run_id}/evidence",
        response_model=list[ResearchEvidenceResponse],
        tags=["evidence"],
    )
    def list_research_run_evidence(
        research_run_id: UUID,
        context: TenantContext = Depends(tenant_dependency),
    ) -> list[ResearchEvidenceResponse]:
        if evidence_store is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="research evidence persistence is not configured",
            )
        try:
            rows = evidence_store.list_for_run(context.workspace_id, research_run_id)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="research evidence persistence unavailable",
            ) from exc
        return [
            ResearchEvidenceResponse(
                id=str(row.id),
                workspace_id=str(row.workspace_id),
                research_run_id=str(row.research_run_id),
                claim_id=str(row.claim_id) if row.claim_id else None,
                plan_hash=row.plan_hash,
                artifact_id=str(row.artifact_id) if row.artifact_id else None,
                claim=row.claim,
                status=row.status,
                provenance=row.provenance,
            )
            for row in rows
        ]


__all__ = [
    "InMemoryResearchEvidenceStore",
    "ResearchEvidenceRecord",
    "ResearchEvidenceResponse",
    "ResearchEvidenceStore",
    "SupabaseResearchEvidenceStore",
    "register_research_evidence_routes",
]
