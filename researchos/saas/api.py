"""Secure HTTP boundary for the QROS SaaS MVP.

This module deliberately does not execute scientific work in an HTTP request.
It creates tenant-scoped jobs and persists immutable dataset versions through
injected storage/persistence adapters.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from researchos.research_core.contracts import FROZEN_XAUUSD_M1_WORKFLOW
from researchos.saas.contracts import (
    DEFAULT_USAGE_POLICIES,
    ResearchJob,
    ResearchJobStatus,
    TenantContext,
)
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
from researchos.saas.store import InMemoryResearchJobStore, ResearchJobStore

REQUEST_ID_HEADER = "X-Request-ID"
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
        """Return a tenant context or raise an authentication/authorization error."""


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


def create_app(
    *,
    auth_provider: AuthProvider | None = None,
    job_store: ResearchJobStore | None = None,
    dataset_store: DatasetStore | None = None,
    dataset_storage: DatasetStorage | None = None,
) -> FastAPI:
    """Build the SaaS API with explicit dependency injection for testing/deployment."""

    auth = auth_provider or UnconfiguredAuthProvider()
    store = job_store or InMemoryResearchJobStore()
    datasets = dataset_store or InMemoryDatasetStore()
    storage = dataset_storage or InMemoryDatasetStorage()
    app = FastAPI(
        title="QROS SaaS API",
        version="1.0.0",
        description="Multi-tenant delivery API for auditable financial research.",
    )
    app.add_middleware(RequestCorrelationMiddleware)

    def current_tenant(authorization: str | None = Header(default=None)) -> TenantContext:
        return auth.authenticate(authorization)

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["system"])
    def readyz() -> dict[str, str]:
        """Report whether the configured application dependencies are usable."""
        if store is None or datasets is None or storage is None:
            raise HTTPException(status_code=503, detail="SaaS persistence is not configured")
        return {"status": "ready"}

    @app.get("/v1/me", response_model=dict[str, str], tags=["identity"])
    def me(tenant: TenantContext = Depends(current_tenant)) -> dict[str, str]:
        return {
            "user_id": str(tenant.user_id),
            "workspace_id": str(tenant.workspace_id),
            "plan": tenant.plan.value,
        }

    @app.post(
        "/v1/datasets",
        response_model=DatasetResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["datasets"],
    )
    def upload_dataset(
        name: str = Form(..., min_length=1, max_length=256),
        file: UploadFile = File(...),
        tenant: TenantContext = Depends(current_tenant),
    ) -> DatasetResponse:
        policy = DEFAULT_USAGE_POLICIES[tenant.plan]
        dataset_id = uuid4()
        version_id = uuid4()
        digest: str
        size: int
        try:
            digest, size = stream_sha256(file.file, policy.max_dataset_bytes)
            if not policy.allows_dataset(size):
                raise ValueError("dataset exceeds plan upload limit")
            dataset = Dataset(
                id=dataset_id,
                workspace_id=tenant.workspace_id,
                name=name.strip(),
                created_by=tenant.user_id,
            )
            storage_path = storage_path_for(tenant.workspace_id, dataset_id, version_id, digest)
            storage.put(storage_path, file.file)
            try:
                persisted_dataset = datasets.create_dataset(dataset)
                version = datasets.create_version(
                    DatasetVersion(
                        id=version_id,
                        dataset_id=dataset_id,
                        version_no=0,
                        content_sha256=digest,
                        storage_path=storage_path,
                        byte_size=size,
                        created_by=tenant.user_id,
                    )
                )
            except Exception:
                storage.remove(storage_path)
                raise
        except ValueError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="dataset persistence failed") from exc

        return DatasetResponse(id=persisted_dataset.id, workspace_id=persisted_dataset.workspace_id, name=persisted_dataset.name, created_by=persisted_dataset.created_by, version=version)

    @app.get("/v1/datasets/{dataset_id}/versions", response_model=list[DatasetVersion], tags=["datasets"])
    def list_dataset_versions(
        dataset_id: UUID,
        tenant: TenantContext = Depends(current_tenant),
    ) -> list[DatasetVersion]:
        return datasets.list_versions(tenant.workspace_id, dataset_id)

    @app.post(
        "/v1/research-runs",
        response_model=ResearchJobResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["research"],
    )
    def create_research_run(
        request: ResearchCreateRequest,
        tenant: TenantContext = Depends(current_tenant),
    ) -> ResearchJob:
        if request.workflow_id != FROZEN_XAUUSD_M1_WORKFLOW:
            raise HTTPException(status_code=400, detail="unsupported workflow")

        policy = DEFAULT_USAGE_POLICIES[tenant.plan]
        if not policy.allows_monthly_runs(store.count_monthly(tenant.workspace_id)):
            raise HTTPException(status_code=402, detail="research run limit reached")
        if not policy.allows_concurrency(store.count_active(tenant.workspace_id)):
            raise HTTPException(status_code=429, detail="concurrent research run limit reached")
        if not datasets.list_versions(tenant.workspace_id, request.dataset_version_id):
            raise HTTPException(status_code=404, detail="dataset version not found")

        job = ResearchJob(
            id=uuid4(),
            workspace_id=tenant.workspace_id,
            dataset_version_id=request.dataset_version_id,
            workflow_id=request.workflow_id,
            status=ResearchJobStatus.QUEUED,
            created_by=tenant.user_id,
        )
        return store.create(job)

    @app.get(
        "/v1/research-runs/{job_id}",
        response_model=ResearchJobResponse,
        tags=["research"],
    )
    def get_research_run(
        job_id: UUID,
        tenant: TenantContext = Depends(current_tenant),
    ) -> ResearchJob:
        job = store.get(tenant.workspace_id, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="research run not found")
        return job

    return app


app = create_app()

__all__ = ["AuthProvider", "RequestCorrelationMiddleware", "app", "create_app"]
