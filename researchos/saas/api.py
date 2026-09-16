"""Secure HTTP boundary for the ResearchOS SaaS MVP.

This module deliberately does not execute scientific work in an HTTP request.
It creates tenant-scoped jobs and leaves execution to a worker adapter.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
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
    dataset_id: str = Field(min_length=1, max_length=256)
    workflow_id: str = Field(default=FROZEN_XAUUSD_M1_WORKFLOW, min_length=1, max_length=128)


class ResearchJobResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    dataset_id: str
    workflow_id: str
    status: ResearchJobStatus


def create_app(
    *,
    auth_provider: AuthProvider | None = None,
    job_store: ResearchJobStore | None = None,
) -> FastAPI:
    """Build the SaaS API with explicit dependency injection for testing/deployment."""

    auth = auth_provider or UnconfiguredAuthProvider()
    store = job_store or InMemoryResearchJobStore()
    app = FastAPI(
        title="ResearchOS SaaS API",
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
        if store is None:
            raise HTTPException(status_code=503, detail="research job store is not configured")
        return {"status": "ready"}

    @app.get("/v1/me", response_model=dict[str, str], tags=["identity"])
    def me(tenant: TenantContext = Depends(current_tenant)) -> dict[str, str]:
        return {
            "user_id": str(tenant.user_id),
            "workspace_id": str(tenant.workspace_id),
            "plan": tenant.plan.value,
        }

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

        job = ResearchJob(
            id=uuid4(),
            workspace_id=tenant.workspace_id,
            dataset_id=request.dataset_id,
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
