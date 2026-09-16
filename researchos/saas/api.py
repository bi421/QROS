"""Secure HTTP boundary for the ResearchOS SaaS MVP.

This module deliberately does not execute scientific work in an HTTP request.
It creates tenant-scoped jobs and leaves execution to a worker adapter.
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from researchos.research_core.contracts import FROZEN_XAUUSD_M1_WORKFLOW
from researchos.saas.config import SaaSSettings
from researchos.saas.contracts import (
    DEFAULT_USAGE_POLICIES,
    ResearchJob,
    ResearchJobStatus,
    TenantContext,
)
from researchos.saas.observability import configure_logging
from researchos.saas.store import InMemoryResearchJobStore, ResearchJobStore

REQUEST_ID_HEADER = "X-Request-ID"


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Attach one bounded correlation ID to every HTTP request and response."""

    def __init__(self, app: object, max_request_id_length: int = 128) -> None:
        super().__init__(app)
        self._max_request_id_length = max_request_id_length

    async def dispatch(self, request: Request, call_next: object) -> Response:
        supplied = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = (
            supplied[: self._max_request_id_length]
            if supplied
            else str(uuid4())
        )
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class RequestSecurityMiddleware(BaseHTTPMiddleware):
    """Apply conservative HTTP security headers and a bounded body-size guard."""

    def __init__(self, app: object, max_body_bytes: int) -> None:
        super().__init__(app)
        self._max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next: object) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared_length = int(content_length)
            except ValueError:
                raise HTTPException(status_code=400, detail="invalid content-length") from None
            if declared_length > self._max_body_bytes:
                raise HTTPException(status_code=413, detail="request body too large")

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
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
    settings: SaaSSettings | None = None,
) -> FastAPI:
    """Build the SaaS API with explicit dependency injection for deployment/tests."""

    runtime = settings or SaaSSettings.from_env()
    configure_logging(runtime.log_level)
    logger = logging.getLogger("researchos.saas.api")

    auth = auth_provider or UnconfiguredAuthProvider()
    store = job_store or InMemoryResearchJobStore()
    app = FastAPI(
        title="ResearchOS SaaS API",
        version="1.0.0",
        description="Multi-tenant delivery API for auditable financial research.",
        docs_url="/docs" if runtime.environment != "production" else None,
        redoc_url="/redoc" if runtime.environment != "production" else None,
    )
    app.add_middleware(
        RequestCorrelationMiddleware,
        max_request_id_length=runtime.request_id_max_length,
    )
    app.add_middleware(
        RequestSecurityMiddleware,
        max_body_bytes=runtime.max_request_body_bytes,
    )

    @app.middleware("http")
    async def access_log(request: Request, call_next: object) -> Response:
        response = await call_next(request)
        logger.info(
            "http_request",
            extra={"request_id": getattr(request.state, "request_id", None)},
        )
        return response

    def current_tenant(authorization: str | None = Header(default=None)) -> TenantContext:
        if runtime.auth_required or authorization:
            return auth.authenticate(authorization)
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
            # Do not reveal whether another tenant owns this ID.
            raise HTTPException(status_code=404, detail="research run not found")
        return job

    return app


app = create_app()

__all__ = [
    "AuthProvider",
    "RequestCorrelationMiddleware",
    "RequestSecurityMiddleware",
    "app",
    "create_app",
]
