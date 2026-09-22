"""HTTP boundary for recording an already-computed governed validation result."""

from __future__ import annotations

from typing import Callable, Protocol
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from researchos.saas.validation import ResearchValidationRecord
from researchos.saas.contracts import TenantContext


class ResearchValidationStore(Protocol):
    def create(self, record: ResearchValidationRecord) -> ResearchValidationRecord: ...
    def get(self, workspace_id: UUID, research_run_id: UUID) -> ResearchValidationRecord | None: ...


class InMemoryResearchValidationStore:
    def __init__(self) -> None:
        self._records: dict[tuple[UUID, UUID], ResearchValidationRecord] = {}

    def create(self, record: ResearchValidationRecord) -> ResearchValidationRecord:
        key = (record.workspace_id, record.research_run_id)
        existing = self._records.get(key)
        if existing is not None:
            if existing.validation_sha256 != record.validation_sha256:
                raise ValueError("research validation already exists with a different digest")
            return existing
        self._records[key] = record
        return record

    def get(self, workspace_id: UUID, research_run_id: UUID) -> ResearchValidationRecord | None:
        record = self._records.get((workspace_id, research_run_id))
        return record


class ResearchValidationRequest(BaseModel):
    result_manifest_sha256: str = Field(min_length=64, max_length=64)
    status: str = Field(min_length=1, max_length=64)
    payload: dict[str, object]


def register_research_validation_routes(
    app: FastAPI,
    *,
    tenant_dependency: Callable[..., TenantContext],
    validation_store: ResearchValidationStore | None,
    job_store: object,
) -> None:
    @app.post("/v1/research-runs/{job_id}/validation", status_code=status.HTTP_201_CREATED, tags=["research"])
    def create_validation(
        job_id: UUID,
        request: ResearchValidationRequest,
        tenant: TenantContext = Depends(tenant_dependency),
    ) -> dict[str, object]:
        if validation_store is None:
            raise HTTPException(status_code=503, detail="research validation persistence is not configured")
        job = job_store.get(tenant.workspace_id, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="research run not found")
        result = job_store.get_result(tenant.workspace_id, job_id)
        if result is None:
            raise HTTPException(status_code=409, detail="research result is not available")
        if result.manifest_sha256 != request.result_manifest_sha256:
            raise HTTPException(status_code=409, detail="result manifest does not match canonical research result")
        payload = ResearchValidationRecord.canonical_payload(request.payload)
        validation_sha256 = ResearchValidationRecord.compute_validation_sha256(payload)
        record = ResearchValidationRecord(
            id=uuid4(),
            workspace_id=tenant.workspace_id,
            research_run_id=job_id,
            result_manifest_sha256=result.manifest_sha256,
            claim_id=job.claim_id,
            plan_hash=job.plan_hash,
            validation_sha256=validation_sha256,
            status=request.status.strip(),
            metrics={
                str(key): float(value)
                for key, value in payload.get("metrics", {}).items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            } if isinstance(payload.get("metrics"), dict) else {},
        )
        try:
            persisted = validation_store.create(record)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "id": str(persisted.id),
            "workspace_id": str(persisted.workspace_id),
            "research_run_id": str(persisted.research_run_id),
            "claim_id": persisted.claim_id,
            "plan_hash": persisted.plan_hash,
            "result_manifest_sha256": persisted.result_manifest_sha256,
            "validation_sha256": persisted.validation_sha256,
            "status": persisted.status,
            "metrics": dict(persisted.metrics),
            "contract_version": persisted.contract_version,
        }

    @app.get("/v1/research-runs/{job_id}/validation", tags=["research"])
    def get_validation(job_id: UUID, tenant: TenantContext = Depends(tenant_dependency)) -> dict[str, object]:
        if validation_store is None:
            raise HTTPException(status_code=503, detail="research validation persistence is not configured")
        record = validation_store.get(tenant.workspace_id, job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="research validation not found")
        return {
            "id": str(record.id),
            "workspace_id": str(record.workspace_id),
            "research_run_id": str(record.research_run_id),
            "claim_id": record.claim_id,
            "plan_hash": record.plan_hash,
            "result_manifest_sha256": record.result_manifest_sha256,
            "validation_sha256": record.validation_sha256,
            "status": record.status,
            "metrics": dict(record.metrics),
            "contract_version": record.contract_version,
        }


__all__ = ["InMemoryResearchValidationStore", "ResearchValidationRequest", "ResearchValidationStore", "register_research_validation_routes"]
