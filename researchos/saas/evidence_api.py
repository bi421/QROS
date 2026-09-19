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
    artifact_id: UUID | None
    claim: str
    status: str
    provenance: dict[str, object]


class ResearchEvidenceStore(Protocol):
    def add(self, record: ResearchEvidenceRecord) -> ResearchEvidenceRecord:
        if record.workspace_id is None:
            raise ValueError("evidence workspace is required")
        run = (
            self._client.table("research_run")
            .select("id")
            .eq("id", str(record.research_run_id))
            .eq("workspace_id", str(record.workspace_id))
            .limit(1)
            .execute()
        )
        if not (run.data or []):
            raise ValueError("research run is not owned by workspace")
        if record.artifact_id is not None:
            artifact = (
                self._client.table("artifact")
                .select("id")
                .eq("id", str(record.artifact_id))
                .eq("research_run_id", str(record.research_run_id))
                .eq("workspace_id", str(record.workspace_id))
                .limit(1)
                .execute()
            )
            if not (artifact.data or []):
                raise ValueError("evidence artifact is not owned by research run")
        result = (
            self._client.table("evidence")
            .insert(
                {
                    "id": str(record.id),
                    "workspace_id": str(record.workspace_id),
                    "research_run_id": str(record.research_run_id),
                    "artifact_id": str(record.artifact_id) if record.artifact_id else None,
                    "claim": record.claim,
                    "status": record.status,
                    "provenance": record.provenance,
                }
            )
            .select("id,workspace_id,research_run_id,artifact_id,claim,status,provenance")
            .execute()
        )
        rows = result.data or []
        if len(rows) != 1:
            raise RuntimeError("evidence persistence returned no unique row")
        return self._record(rows[0])

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
                row for row in self._rows.values()
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
            artifact_id=UUID(str(artifact)) if artifact else None,
            claim=str(row["claim"]),
            status=str(row["status"]),
            provenance=dict(provenance),
        )

    def list_for_run(self, workspace_id: UUID, research_run_id: UUID) -> list[ResearchEvidenceRecord]:
        run = (
            self._client.table("research_run")
            .select("id")
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
        return [self._record(row) for row in (result.data or [])]


class ResearchEvidenceResponse(BaseModel):
    id: str
    workspace_id: str
    research_run_id: str
    artifact_id: str | None
    claim: str
    status: str
    provenance: dict[str, object]


def register_research_evidence_routes(router: Any, *, tenant_dependency: Any, evidence_store: ResearchEvidenceStore | None) -> None:
    @router.get("/v1/research-runs/{research_run_id}/evidence", response_model=list[ResearchEvidenceResponse], tags=["evidence"])
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
