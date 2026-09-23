"""Tenant-scoped Evidence read API for the QROS Golden Path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from researchos.saas.contracts import TenantContext
from researchos.saas.auth.authorization import require_permission
from researchos.saas.pagination import PaginationParameterError, pagination_envelope, parse_list_query, validate_filter_keys


@dataclass(frozen=True)
class ResearchEvidenceRecord:
    id: UUID
    workspace_id: UUID
    research_run_id: UUID
    artifact_id: UUID | None
    claim: str
    status: str
    provenance: dict[str, object]
    claim_id: UUID | None = None
    plan_hash: str | None = None


class ResearchEvidenceStore(Protocol):
    def list_for_claim(self, workspace_id: UUID, claim_id: str) -> list[ResearchEvidenceRecord]:
        ...

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

    def list_for_claim(self, workspace_id: UUID, claim_id: str) -> list[ResearchEvidenceRecord]:
        return sorted(
            (row for row in self._rows.values() if row.workspace_id == workspace_id and str(row.claim_id) == claim_id),
            key=lambda row: str(row.id),
        )

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

    def list_for_claim(self, workspace_id: UUID, claim_id: str) -> list[ResearchEvidenceRecord]:
        runs = (
            self._client.table("research_run")
            .select("id,claim_id,plan_hash")
            .eq("workspace_id", str(workspace_id))
            .eq("claim_id", claim_id)
            .execute()
        )
        records: list[ResearchEvidenceRecord] = []
        for run in (runs.data or []):
            run_id = UUID(str(run["id"]))
            result = (
                self._client.table("evidence")
                .select("id,workspace_id,research_run_id,artifact_id,claim,status,provenance")
                .eq("workspace_id", str(workspace_id))
                .eq("research_run_id", str(run_id))
                .order("id")
                .execute()
            )
            for row in (result.data or []):
                row["claim_id"] = run.get("claim_id")
                row["plan_hash"] = run.get("plan_hash")
                records.append(self._record(row))
        return sorted(records, key=lambda row: str(row.id))

    def list_for_run(self, workspace_id: UUID, research_run_id: UUID) -> list[ResearchEvidenceRecord]:
        run = (
            self._client.table("research_run")
            .select("id,claim_id,plan_hash")
            .eq("id", str(research_run_id))
            .eq("workspace_id", str(workspace_id))
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
        if not (run.data or []):
            return []
        result = (
            self._client.table("evidence")
            .select("id,workspace_id,research_run_id,artifact_id,claim,status,provenance")
            .eq("workspace_id", str(workspace_id))
            .is_("deleted_at", "null")
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


def _evidence_response(row: ResearchEvidenceRecord) -> ResearchEvidenceResponse:
    return ResearchEvidenceResponse(
        id=str(row.id), workspace_id=str(row.workspace_id), research_run_id=str(row.research_run_id),
        claim_id=str(row.claim_id) if row.claim_id else None, plan_hash=row.plan_hash,
        artifact_id=str(row.artifact_id) if row.artifact_id else None, claim=row.claim,
        status=row.status, provenance=row.provenance,
    )

def register_research_evidence_routes(
    router: Any,
    *,
    tenant_dependency: Any,
    evidence_store: ResearchEvidenceStore | None,
) -> None:
    def _evidence_page(rows: list[ResearchEvidenceRecord], *, page: str, page_size: str, sort_by: str, sort_order: str, status_filter: str | None, tenant_filter: str | None, request: Request, context: TenantContext) -> dict[str, object]:
        try:
            validate_filter_keys(
                {key.removeprefix("filter[").removesuffix("]"): value for key, value in request.query_params.items() if key.startswith("filter[")},
                allowed=frozenset({"status", "tenant_id"}),
            )
            query = parse_list_query(page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order, tenant_id=tenant_filter, allowed_sort_fields=frozenset({"created_at", "status"}), status=status_filter)
        except PaginationParameterError as exc:
            raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)}) from exc
        if tenant_filter is not None and tenant_filter != str(context.workspace_id):
            rows = []
        if query.status is not None:
            rows = [row for row in rows if row.status == query.status]
        if query.sort_by == "status":
            rows = sorted(rows, key=lambda row: row.status, reverse=query.sort_order == "desc")
        else:
            rows = sorted(rows, key=lambda row: str(row.id), reverse=query.sort_order == "desc")
        total = len(rows)
        data = [_evidence_response(row).model_dump(mode="json") for row in rows[query.offset:query.offset + query.page_size]]
        return pagination_envelope(data=data, page=query.page, page_size=query.page_size, total=total, request_id=request.state.request_id)

    @router.get(
        "/v1/research-runs/{research_run_id}/evidence",
        response_model=dict[str, object],
        tags=["evidence"],
    )
    @require_permission("evidence", "list")
    def list_research_run_evidence(
        research_run_id: UUID,
        page: str = "1",
        page_size: str = "20",
        sort_by: str = "created_at",
        sort_order: str = "desc",
        status_filter: str | None = Query(default=None, alias="filter[status]"),
        tenant_filter: str | None = Query(default=None, alias="filter[tenant_id]"),
        request: Request = None,
        context: TenantContext = Depends(tenant_dependency),
    ) -> dict[str, object]:
        if evidence_store is None:
            raise HTTPException(status_code=503, detail="research evidence persistence is not configured")
        try:
            rows = evidence_store.list_for_run(context.workspace_id, research_run_id)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="research evidence persistence unavailable") from exc
        return _evidence_page(rows, page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order, status_filter=status_filter, tenant_filter=tenant_filter, request=request, context=context)
    @router.get(
        "/v1/research-claims/{claim_id}/evidence-graph",
        response_model=dict[str, object],
        tags=["evidence"],
        responses={404: {"description": "Claim not visible in workspace"}},
    )
    @require_permission("evidence", "read")
    def get_claim_evidence_graph(
        claim_id: str,
        page: str = "1",
        page_size: str = "20",
        sort_by: str = "created_at",
        sort_order: str = "desc",
        status_filter: str | None = Query(default=None, alias="filter[status]"),
        tenant_filter: str | None = Query(default=None, alias="filter[tenant_id]"),
        request: Request = None,
        context: TenantContext = Depends(tenant_dependency),
    ) -> dict[str, object]:
        if not claim_id.strip() or len(claim_id) > 256:
            raise HTTPException(status_code=422, detail="invalid claim id")
        if evidence_store is None:
            raise HTTPException(status_code=503, detail="research evidence persistence is not configured")
        try:
            rows = evidence_store.list_for_claim(context.workspace_id, claim_id)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="research evidence persistence unavailable") from exc
        return _evidence_page(rows, page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order, status_filter=status_filter, tenant_filter=tenant_filter, request=request, context=context)

    @router.get(
        "/v1/claims/{claim_id}/evidence_graph",
        response_model=dict[str, object],
        tags=["evidence"],
    )
    @require_permission("evidence", "read")
    def get_claim_evidence_graph_compat(
        claim_id: str,
        page: str = "1",
        page_size: str = "20",
        sort_by: str = "created_at",
        sort_order: str = "desc",
        status_filter: str | None = Query(default=None, alias="filter[status]"),
        tenant_filter: str | None = Query(default=None, alias="filter[tenant_id]"),
        request: Request = None,
        context: TenantContext = Depends(tenant_dependency),
    ) -> dict[str, object]:
        if not claim_id.strip() or len(claim_id) > 256:
            raise HTTPException(status_code=422, detail="invalid claim id")
        if evidence_store is None:
            raise HTTPException(status_code=503, detail="research evidence persistence is not configured")
        rows = evidence_store.list_for_claim(context.workspace_id, claim_id)
        return _evidence_page(rows, page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order, status_filter=status_filter, tenant_filter=tenant_filter, request=request, context=context)



__all__ = [
    "InMemoryResearchEvidenceStore",
    "ResearchEvidenceRecord",
    "ResearchEvidenceResponse",
    "ResearchEvidenceStore",
    "SupabaseResearchEvidenceStore",
    "register_research_evidence_routes",
]
