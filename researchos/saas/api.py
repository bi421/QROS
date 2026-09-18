"""Secure HTTP boundary for the QROS SaaS MVP."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4
import hashlib
import json

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from researchos.research_core.contracts import FROZEN_XAUUSD_M1_WORKFLOW
from researchos.saas.contracts import DEFAULT_USAGE_POLICIES, ResearchJob, ResearchJobStatus, TenantContext
from researchos.saas.datasets import (
    Dataset,
    DatasetStorage,
    DatasetStore,
    DatasetVersion,
    InMemoryDatasetStorage,
    InMemoryDatasetStore,
    storage_path_for,
    stream_sha256,
)
from researchos.saas.queue import InMemoryResearchJobQueue, ResearchJobQueue
from researchos.saas.store import InMemoryResearchJobStore, ResearchJobStore
from researchos.saas.idempotency import (
    IdempotencyConflict,
    IdempotencyRecord,
    IdempotencyStore,
    InMemoryIdempotencyStore,
    MAX_IDEMPOTENCY_KEY_LENGTH,
)
from researchos.saas.rate_limit import FixedWindowRateLimiter

REQUEST_ID_HEADER = "X-Request-ID"
IDEMPOTENCY_HEADER = "Idempotency-Key"
MAX_REQUEST_ID_LENGTH = 128


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Attach one bounded correlation ID to every HTTP request and response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        supplied = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = supplied[:MAX_REQUEST_ID_LENGTH] if supplied else str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class AuthProvider(Protocol):
    """Authenticate a request and resolve its authorized workspace."""

    def authenticate(self, authorization: str | None) -> TenantContext:
        ...


class UnconfiguredAuthProvider:
    """Fail-closed default; production must install a real identity provider."""

    def authenticate(self, authorization: str | None) -> TenantContext:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SaaS authentication provider is not configured",
        )


class ResearchCreateRequest(BaseModel):
    dataset_version_id: UUID
    workflow_id: str = Field(default=FROZEN_XAUUSD_M1_WORKFLOW, min_length=1, max_length=128)


class ResearchJobResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    dataset_version_id: UUID
    workflow_id: str
    status: ResearchJobStatus


class DatasetResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    created_by: UUID
    version: DatasetVersion


def _research_job_response(job: ResearchJob) -> ResearchJobResponse:
    """Serialize the domain dataclass explicitly at the HTTP boundary."""
    return ResearchJobResponse(
        id=job.id,
        workspace_id=job.workspace_id,
        dataset_version_id=job.dataset_version_id,
        workflow_id=job.workflow_id,
        status=job.status,
    )


def create_app(
    *,
    auth_provider: AuthProvider | None = None,
    job_store: ResearchJobStore | None = None,
    dataset_store: DatasetStore | None = None,
    dataset_storage: DatasetStorage | None = None,
    job_queue: ResearchJobQueue | None = None,
    idempotency_store: IdempotencyStore | None = None,
) -> FastAPI:
    """Build the SaaS API with explicit dependency injection for testing/deployment."""

    auth = auth_provider or UnconfiguredAuthProvider()
    store = job_store or InMemoryResearchJobStore()
    datasets = dataset_store or InMemoryDatasetStore()
    storage = dataset_storage or InMemoryDatasetStorage()
    queue = job_queue or InMemoryResearchJobQueue()
    idempotency = idempotency_store or InMemoryIdempotencyStore()
    rate_limiter = FixedWindowRateLimiter(limit=120, window_seconds=60)
    app = FastAPI(
        title="QROS SaaS API",
        version="1.0.0",
        description="Multi-tenant delivery API for auditable financial research.",
    )
    app.add_middleware(RequestCorrelationMiddleware)

    def current_tenant(authorization: str | None = Header(default=None)) -> TenantContext:
        return auth.authenticate(authorization)

    def require_rate_limit(request: Request, authorization: str | None) -> None:
        source = authorization or (request.client.host if request.client else "anonymous")
        principal = hashlib.sha256(source.encode()).hexdigest()
        if not rate_limiter.allow(principal):
            raise HTTPException(status_code=429, detail="rate limit exceeded")

    def request_fingerprint(payload: object) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(encoded).hexdigest()

    def persist_version(*, dataset_id: UUID, tenant: TenantContext, file: UploadFile) -> DatasetVersion:
        policy = DEFAULT_USAGE_POLICIES[tenant.plan]
        try:
            digest, size = stream_sha256(file.file, policy.max_dataset_bytes)
            if not policy.allows_dataset(size):
                raise ValueError("dataset exceeds plan upload limit")
            storage_path = storage_path_for(tenant.workspace_id, dataset_id, digest)
            storage.put(storage_path, file.file)
            try:
                version = datasets.create_version(
                    DatasetVersion(
                        id=uuid4(),
                        dataset_id=dataset_id,
                        version_no=len(datasets.list_versions(tenant.workspace_id, dataset_id)) + 1,
                        content_sha256=digest,
                        storage_path=storage_path,
                        byte_size=size,
                        created_by=tenant.user_id,
                    )
                )
            except Exception:
                storage.remove(storage_path)
                raise
            return version
        except ValueError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="dataset version persistence failed") from exc

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["system"])
    def readyz() -> dict[str, str]:
        if store is None or datasets is None or storage is None or queue is None:
            raise HTTPException(status_code=503, detail="SaaS persistence is not configured")
        return {"status": "ready"}

    @app.get("/v1/me", response_model=dict[str, str], tags=["identity"])
    def me(tenant: TenantContext = Depends(current_tenant)) -> dict[str, str]:
        return {"user_id": str(tenant.user_id), "workspace_id": str(tenant.workspace_id), "plan": tenant.plan.value}

    @app.post("/v1/datasets", response_model=DatasetResponse, status_code=201, tags=["datasets"])
    def upload_dataset(
        name: str = Form(..., min_length=1, max_length=256),
        file: UploadFile = File(...),
        tenant: TenantContext = Depends(current_tenant),
    ) -> DatasetResponse:
        dataset = Dataset(id=uuid4(), workspace_id=tenant.workspace_id, name=name.strip(), created_by=tenant.user_id)
        policy = DEFAULT_USAGE_POLICIES[tenant.plan]
        try:
            digest, size = stream_sha256(file.file, policy.max_dataset_bytes)
            if not policy.allows_dataset(size):
                raise ValueError("dataset exceeds plan upload limit")
            storage_path = storage_path_for(tenant.workspace_id, dataset.id, digest)
            storage.put(storage_path, file.file)
            try:
                persisted_dataset = datasets.create_dataset(dataset)
                version = datasets.create_version(
                    DatasetVersion(
                        id=uuid4(),
                        dataset_id=dataset.id,
                        version_no=1,
                        content_sha256=digest,
                        storage_path=storage_path,
                        byte_size=size,
                        created_by=tenant.user_id,
                    )
                )
            except Exception:
                try:
                    datasets.delete_dataset(tenant.workspace_id, dataset.id)
                finally:
                    storage.remove(storage_path)
                raise
        except ValueError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="dataset persistence failed") from exc

        return DatasetResponse(
            id=persisted_dataset.id,
            workspace_id=persisted_dataset.workspace_id,
            name=persisted_dataset.name,
            created_by=persisted_dataset.created_by,
            version=version,
        )

    @app.post("/v1/datasets/{dataset_id}/versions", response_model=DatasetVersion, status_code=201, tags=["datasets"])
    def upload_dataset_version(
        dataset_id: UUID,
        file: UploadFile = File(...),
        tenant: TenantContext = Depends(current_tenant),
    ) -> DatasetVersion:
        if datasets.get_dataset(tenant.workspace_id, dataset_id) is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        return persist_version(dataset_id=dataset_id, tenant=tenant, file=file)

    @app.get("/v1/datasets/{dataset_id}/versions", response_model=list[DatasetVersion], tags=["datasets"])
    def list_dataset_versions(
        dataset_id: UUID,
        tenant: TenantContext = Depends(current_tenant),
    ) -> list[DatasetVersion]:
        return datasets.list_versions(tenant.workspace_id, dataset_id)

    @app.post("/v1/research-runs", response_model=ResearchJobResponse, status_code=202, tags=["research"])
    def create_research_run(
        request: ResearchCreateRequest,
        request_obj: Request,
        tenant: TenantContext = Depends(current_tenant),
        idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
        authorization: str | None = Header(default=None),
    ) -> Response:
        require_rate_limit(request_obj, authorization)
        if request.workflow_id != FROZEN_XAUUSD_M1_WORKFLOW:
            raise HTTPException(status_code=400, detail="unsupported workflow")
        if not idempotency_key:
            raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise HTTPException(status_code=400, detail="invalid Idempotency-Key")
        fingerprint = request_fingerprint({
            "dataset_version_id": str(request.dataset_version_id),
            "workflow_id": request.workflow_id,
        })
        replay = idempotency.get(tenant.workspace_id, idempotency_key)
        if replay is not None:
            if replay.request_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="idempotency key reused with different request")
            return JSONResponse(status_code=replay.status_code, content=replay.response_body)
        policy = DEFAULT_USAGE_POLICIES[tenant.plan]
        if not policy.allows_monthly_runs(store.count_monthly(tenant.workspace_id)):
            raise HTTPException(status_code=402, detail="research run limit reached")
        if not policy.allows_concurrency(store.count_active(tenant.workspace_id)):
            raise HTTPException(status_code=429, detail="concurrent research run limit reached")
        version = datasets.get_version(tenant.workspace_id, request.dataset_version_id)
        if version is None:
            raise HTTPException(status_code=404, detail="dataset version not found")

        job = ResearchJob(
            id=uuid4(),
            workspace_id=tenant.workspace_id,
            dataset_version_id=version.id,
            workflow_id=request.workflow_id,
            status=ResearchJobStatus.QUEUED,
            created_by=tenant.user_id,
        )
        created = store.create(job)
        try:
            queue.enqueue(tenant.workspace_id, created.id)
        except Exception as exc:
            try:
                store.transition(
                    tenant.workspace_id,
                    created.id,
                    ResearchJobStatus.QUEUED,
                    ResearchJobStatus.FAILED,
                )
            except Exception:
                pass
            raise HTTPException(status_code=503, detail="research job queue unavailable") from exc
        body = _research_job_response(created).model_dump(mode="json")
        try:
            idempotency.put(IdempotencyRecord(tenant.workspace_id, idempotency_key, fingerprint, 202, body))
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(status_code=202, content=body)

    @app.get("/v1/research-runs/{job_id}", response_model=ResearchJobResponse, tags=["research"])
    def get_research_run(job_id: UUID, tenant: TenantContext = Depends(current_tenant)) -> ResearchJobResponse:
        job = store.get(tenant.workspace_id, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="research run not found")
        return _research_job_response(job)

    return app


app = create_app()

__all__ = ["AuthProvider", "RequestCorrelationMiddleware", "app", "create_app"]
