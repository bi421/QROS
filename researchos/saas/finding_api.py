"""HTTP boundary for recording an already-validated research finding."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from researchos.saas.finding import ResearchFindingRecord, VALIDATED_STATUS
from researchos.saas.pagination import PaginationParameterError, pagination_envelope, parse_list_query
from researchos.saas.auth.authorization import require_permission


class ResearchFindingStore(Protocol):
    def create(self, record: ResearchFindingRecord) -> ResearchFindingRecord: ...
    def get(self, workspace_id: UUID, research_run_id: UUID) -> ResearchFindingRecord | None: ...
    def list(self, workspace_id: UUID, *, limit: int = 20, offset: int = 0, sort_by: str = "created_at", sort_order: str = "desc", status: str | None = None) -> tuple[list[ResearchFindingRecord], int]: ...


class InMemoryResearchFindingStore:
    def __init__(self) -> None:
        self._records: dict[tuple[UUID, UUID], ResearchFindingRecord] = {}

    def create(self, record: ResearchFindingRecord) -> ResearchFindingRecord:
        key = (record.workspace_id, record.research_run_id)
        existing = self._records.get(key)
        if existing is not None:
            if existing.finding_sha256 != record.finding_sha256:
                raise ValueError("research finding already exists with a different digest")
            return existing
        self._records[key] = record
        return record

    def get(self, workspace_id: UUID, research_run_id: UUID) -> ResearchFindingRecord | None:
        return self._records.get((workspace_id, research_run_id))

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
        records = [
            record for (row_workspace, _), record in self._records.items()
            if row_workspace == workspace_id and (status is None or record.status == status)
        ]
        key = (lambda item: item.created_at) if sort_by == "created_at" else (lambda item: item.status)
        records.sort(key=key, reverse=sort_order == "desc")
        return records[offset:offset + limit], len(records)


class ResearchFindingRequest(BaseModel):
    validation_sha256: str = Field(min_length=64, max_length=64)
    payload: dict[str, object]


def register_research_finding_routes(
    app: FastAPI,
    *,
    tenant_dependency,
    finding_store: ResearchFindingStore | None,
    validation_store,
) -> None:
    @app.post("/v1/research-runs/{job_id}/finding", status_code=status.HTTP_201_CREATED, tags=["research"])
    @require_permission("finding", "create")
    def create_finding(
        job_id: UUID,
        request: ResearchFindingRequest,
        tenant=Depends(tenant_dependency),
    ) -> dict[str, object]:
        if finding_store is None:
            raise HTTPException(status_code=503, detail="research finding persistence is not configured")
        validation = validation_store.get(tenant.workspace_id, job_id)
        if validation is None:
            raise HTTPException(status_code=404, detail="research validation not found")
        if validation.status != VALIDATED_STATUS:
            raise HTTPException(status_code=409, detail="only VALIDATED research results may produce a finding")
        if validation.validation_sha256 != request.validation_sha256.strip().lower():
            raise HTTPException(status_code=409, detail="validation digest does not match canonical validation")
        payload = ResearchFindingRecord.canonical_payload(request.payload)
        finding_sha256 = ResearchFindingRecord.compute_finding_sha256(payload)
        record = ResearchFindingRecord(
            id=uuid4(),
            workspace_id=tenant.workspace_id,
            research_run_id=job_id,
            validation_id=validation.id,
            result_manifest_sha256=validation.result_manifest_sha256,
            validation_sha256=validation.validation_sha256,
            claim_id=validation.claim_id,
            plan_hash=validation.plan_hash,
            finding_sha256=finding_sha256,
            status=VALIDATED_STATUS,
            payload=payload,
        )
        try:
            persisted = finding_store.create(record)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _response(persisted)

    @app.get("/v1/findings", tags=["research"])
    def list_findings(
        page: str = "1",
        page_size: str = "20",
        sort_by: str = "created_at",
        sort_order: str = "desc",
        status_filter: str | None = Query(default=None, alias="filter[status]"),
        tenant=Depends(tenant_dependency),
    ) -> dict[str, object]:
        if finding_store is None:
            raise HTTPException(status_code=503, detail="research finding persistence is not configured")
        try:
            query = parse_list_query(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
                status=status_filter,
                allowed_sort_fields=frozenset({"created_at", "status"}),
            )
            records, total = finding_store.list(
                tenant.workspace_id,
                limit=query.page_size,
                offset=query.offset,
                sort_by=query.sort_by,
                sort_order=query.sort_order,
                status=query.status,
            )
        except PaginationParameterError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_SORT" if "sort" in str(exc) else "INVALID_FILTER", "message": str(exc)},
            ) from exc
        return pagination_envelope(
            data=[_response(record) for record in records],
            page=query.page,
            page_size=query.page_size,
            total=total,
        )

    @app.get("/v1/research-runs/{job_id}/finding", tags=["research"])
    @require_permission("finding", "read")
    def get_finding(job_id: UUID, tenant=Depends(tenant_dependency)) -> dict[str, object]:
        if finding_store is None:
            raise HTTPException(status_code=503, detail="research finding persistence is not configured")
        record = finding_store.get(tenant.workspace_id, job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="research finding not found")
        return _response(record)


def _response(record: ResearchFindingRecord) -> dict[str, object]:
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


__all__ = ["InMemoryResearchFindingStore", "ResearchFindingRequest", "ResearchFindingStore", "register_research_finding_routes"]
