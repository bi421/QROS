"""Secure HTTP boundary for the QROS SaaS MVP."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4
import hashlib
import json
import logging

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, Response
from researchos.saas.api_middleware import RequestContextMiddleware
from researchos.saas.observability import (
    configure_logging,
    jobs_created_total,
    jobs_failed_total,
    metrics_text,
)
from researchos.saas.auth.permissions import Action, Resource, require_permission

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
from researchos.saas.queue import InMemoryResearchJobQueue, ResearchJobQueue
from researchos.saas.store import InMemoryResearchJobStore, ResearchJobStore
from researchos.saas.idempotency import (
    IdempotencyStore,
    MAX_IDEMPOTENCY_KEY_LENGTH,
)
from researchos.saas.rate_limit import FixedWindowRateLimiter, RateLimiter
from researchos.saas.pagination import paginate, validate_filter_tenant_id
from researchos.saas.billing import (
    BillingEventConflict,
    BillingEventStore,
    BillingSignatureError,
    parse_billing_event,
    verify_hmac_signature,
)

REQUEST_ID_HEADER = "X-Request-ID"
IDEMPOTENCY_HEADER = "Idempotency-Key"
MAX_REQUEST_ID_LENGTH = 128

logger = logging.getLogger(__name__)
configure_logging()


def _error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        402: "payment_required",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        413: "payload_too_large",
        422: "validation_error",
        429: "rate_limited",
        500: "internal_error",
        503: "service_unavailable",
    }.get(status_code, "http_error")


def _error_payload(
    request: Request, status_code: int, detail: object, details: object | None = None
) -> dict[str, object]:
    message = detail if isinstance(detail, str) else "request failed"
    code = (
        detail
        if isinstance(detail, str) and detail.startswith("INVALID_")
        else _error_code(status_code)
    )
    error: dict[str, object] = {
        "code": code,
        "message": message,
        "request_id": getattr(request.state, "request_id", None),
        "correlation_id": request.headers.get("X-Correlation-ID")
        or getattr(request.state, "request_id", None),
    }
    if details is not None:
        error["details"] = details
    return {
        "detail": detail,
        "code": code,
        "request_id": getattr(request.state, "request_id", None),
        "error": error,
    }


def _validate_dataset_name(name: str) -> str:
    """Reject path-like dataset names before they cross any storage boundary."""
    normalized = name.strip()
    if not normalized or "/" in normalized or "\\" in normalized or ".." in normalized:
        raise HTTPException(status_code=400, detail="INVALID_PATH")
    return normalized


class AuthProvider(Protocol):
    """Authenticate a request and resolve its authorized workspace."""

    def authenticate(self, authorization: str | None) -> TenantContext: ...


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
    billing_store: BillingEventStore | None = None,
    billing_webhook_secret: str | None = None,
    rate_limiter: RateLimiter | None = None,
) -> FastAPI:
    """Build the SaaS API with explicit dependency injection for testing/deployment."""

    auth = auth_provider or UnconfiguredAuthProvider()
    store = job_store or InMemoryResearchJobStore()
    datasets = dataset_store or InMemoryDatasetStore()
    storage = dataset_storage or InMemoryDatasetStorage()
    queue = job_queue or InMemoryResearchJobQueue()
    limiter = rate_limiter or FixedWindowRateLimiter(limit=120, window_seconds=60)
    billing = billing_store
    app = FastAPI(
        title="QROS SaaS API",
        version="1.0.0",
        description="Multi-tenant delivery API for auditable financial research.",
    )
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content=_error_payload(request, exc.status_code, exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        payload = _error_payload(request, 400, exc.errors())
        payload["code"] = "validation_error"
        error = payload["error"]
        if isinstance(error, dict):
            error["code"] = "validation_error"
            error["message"] = "Request validation failed"
        return JSONResponse(status_code=400, content=payload)

    @app.exception_handler(Exception)
    async def internal_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.exception("unhandled request exception request_id=%s", request_id)
        return JSONResponse(
            status_code=500,
            headers={REQUEST_ID_HEADER: request_id} if request_id else None,
            content=_error_payload(request, 500, "Internal error"),
        )

    def current_tenant(authorization: str | None = Header(default=None)) -> TenantContext:
        return auth.authenticate(authorization)

    def require_rate_limit(tenant: TenantContext) -> None:
        principal = hashlib.sha256(f"workspace:{tenant.workspace_id}".encode()).hexdigest()
        try:
            allowed = limiter.allow(principal)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="rate limiting service unavailable",
            ) from exc
        if not allowed:
            raise HTTPException(status_code=429, detail="rate limit exceeded")

    def request_fingerprint(payload: object) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(encoded).hexdigest()

    def persist_version(
        *, dataset_id: UUID, tenant: TenantContext, file: UploadFile
    ) -> DatasetVersion:
        policy = DEFAULT_USAGE_POLICIES[tenant.plan]
        try:
            digest, size = stream_sha256(file.file, policy.max_dataset_bytes)
            if not policy.allows_dataset(size):
                raise ValueError("dataset exceeds plan upload limit")
            existing_versions = datasets.list_versions(tenant.workspace_id, dataset_id)
            duplicate = next((v for v in existing_versions if v.content_sha256 == digest), None)
            if duplicate is not None:
                return duplicate
            next_version = max((v.version_no for v in existing_versions), default=0) + 1
            storage_path = storage_path_for(tenant.workspace_id, digest, next_version)
            object_created = False
            if not storage.exists(storage_path):
                storage.put(storage_path, file.file)
                object_created = True
            try:
                version = datasets.create_version(
                    tenant.workspace_id,
                    DatasetVersion(
                        id=uuid4(),
                        dataset_id=dataset_id,
                        version_no=next_version,
                        content_sha256=digest,
                        storage_path=storage_path,
                        byte_size=size,
                        created_by=tenant.user_id,
                    ),
                )
            except Exception:
                if object_created:
                    storage.remove(storage_path)
                raise
            return version
        except ValueError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise RuntimeError("dataset version persistence failed") from exc

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False, tags=["system"])
    def metrics() -> Response:
        return Response(content=metrics_text(), media_type="text/plain; version=0.0.4")

    @app.get("/readyz", tags=["system"])
    def readyz() -> dict[str, str]:
        if store is None or datasets is None or storage is None or queue is None:
            raise HTTPException(status_code=503, detail="SaaS persistence is not configured")
        return {"status": "ready"}

    @app.post("/v1/billing/webhook", status_code=200, tags=["billing"])
    async def billing_webhook(
        request: Request,
        x_billing_signature: str | None = Header(default=None, alias="X-Billing-Signature"),
        x_billing_provider: str | None = Header(default=None, alias="X-Billing-Provider"),
    ) -> dict[str, str]:
        if billing is None or not billing_webhook_secret:
            raise HTTPException(status_code=503, detail="billing webhook is not configured")
        if not x_billing_signature or not x_billing_provider:
            raise HTTPException(
                status_code=400, detail="billing signature and provider are required"
            )
        payload = await request.body()
        try:
            verify_hmac_signature(payload, x_billing_signature, billing_webhook_secret)
            event = parse_billing_event(payload)
        except BillingSignatureError as exc:
            raise HTTPException(
                status_code=401, detail="invalid billing webhook signature"
            ) from exc
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="invalid billing event") from exc
        payload_sha256 = hashlib.sha256(payload).hexdigest()
        try:
            processed = billing.process(event, x_billing_provider.strip()[:64], payload_sha256)
        except BillingEventConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise RuntimeError("billing event processing failed") from exc
        return {"status": "processed" if processed else "replayed"}

    @app.get("/v1/me", response_model=dict[str, str], tags=["identity"])
    def me(tenant: TenantContext = Depends(current_tenant)) -> dict[str, str]:
        return {
            "user_id": str(tenant.user_id),
            "workspace_id": str(tenant.workspace_id),
            "plan": tenant.plan.value,
        }

    @app.post("/v1/datasets", response_model=DatasetResponse, status_code=201, tags=["datasets"])
    @require_permission(Resource.DATASET, Action.CREATE)
    def upload_dataset(
        name: str = Form(..., min_length=1, max_length=256),
        file: UploadFile = File(...),
        tenant: TenantContext = Depends(current_tenant),
    ) -> DatasetResponse:
        dataset = Dataset(
            id=uuid4(),
            workspace_id=tenant.workspace_id,
            name=_validate_dataset_name(name),
            created_by=tenant.user_id,
        )
        policy = DEFAULT_USAGE_POLICIES[tenant.plan]
        try:
            digest, size = stream_sha256(file.file, policy.max_dataset_bytes)
            if not policy.allows_dataset(size):
                raise ValueError("dataset exceeds plan upload limit")
            storage_path = storage_path_for(tenant.workspace_id, digest, 1)
            object_created = False
            if not storage.exists(storage_path):
                storage.put(storage_path, file.file)
                object_created = True
            try:
                persisted_dataset = datasets.create_dataset(tenant.workspace_id, dataset)
                version = datasets.create_version(
                    tenant.workspace_id,
                    DatasetVersion(
                        id=uuid4(),
                        dataset_id=dataset.id,
                        version_no=1,
                        content_sha256=digest,
                        storage_path=storage_path,
                        byte_size=size,
                        created_by=tenant.user_id,
                    ),
                )
            except Exception:
                try:
                    datasets.delete_dataset(tenant.workspace_id, dataset.id)
                finally:
                    if object_created:
                        storage.remove(storage_path)
                raise
        except ValueError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except Exception as exc:
            raise RuntimeError("dataset persistence failed") from exc

        return DatasetResponse(
            id=persisted_dataset.id,
            workspace_id=persisted_dataset.workspace_id,
            name=persisted_dataset.name,
            created_by=persisted_dataset.created_by,
            version=version,
        )

    @app.post(
        "/v1/datasets/{dataset_id}/versions",
        response_model=DatasetVersion,
        status_code=201,
        tags=["datasets"],
    )
    @require_permission(Resource.DATASET_VERSION, Action.CREATE)
    def upload_dataset_version(
        dataset_id: UUID,
        file: UploadFile = File(...),
        tenant: TenantContext = Depends(current_tenant),
    ) -> DatasetVersion:
        if datasets.get_dataset(tenant.workspace_id, dataset_id) is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        return persist_version(dataset_id=dataset_id, tenant=tenant, file=file)

    @app.get("/v1/datasets/{dataset_id}/versions", tags=["datasets"])
    @require_permission(Resource.DATASET_VERSION, Action.LIST)
    def list_dataset_versions(
        dataset_id: UUID,
        request: Request,
        page: int = Query(default=1),
        page_size: int = Query(default=20),
        sort_by: str = Query(default="version_no"),
        sort_order: str = Query(default="desc"),
        filter_status: str | None = Query(default=None, alias="filter[status]"),
        filter_tenant_id: UUID | None = Query(default=None, alias="filter[tenant_id]"),
        tenant: TenantContext = Depends(current_tenant),
    ) -> dict[str, object]:
        if page < 1 or page_size < 1 or page_size > 100:
            raise HTTPException(status_code=400, detail="INVALID_PAGINATION")
        validate_filter_tenant_id(filter_tenant_id, tenant.workspace_id)
        if filter_status is not None:
            raise HTTPException(status_code=400, detail="INVALID_FILTER")
        if sort_order not in {"asc", "desc"}:
            raise HTTPException(status_code=400, detail="INVALID_SORT")
        items = datasets.list_versions(tenant.workspace_id, dataset_id)
        if sort_by not in {"version_no", "content_sha256", "byte_size"}:
            raise HTTPException(status_code=400, detail="INVALID_SORT")
        return paginate(
            items,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            request_id=getattr(request.state, "request_id", None),
        )

    @app.post(
        "/v1/research-runs", response_model=ResearchJobResponse, status_code=202, tags=["research"]
    )
    @require_permission(Resource.JOB, Action.CREATE)
    def create_research_run(
        request: ResearchCreateRequest,
        tenant: TenantContext = Depends(current_tenant),
        idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    ) -> Response:
        require_rate_limit(tenant)
        if request.workflow_id != FROZEN_XAUUSD_M1_WORKFLOW:
            raise HTTPException(status_code=400, detail="unsupported workflow")
        if not idempotency_key:
            raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise HTTPException(status_code=400, detail="invalid Idempotency-Key")
        fingerprint = request_fingerprint(
            {
                "dataset_version_id": str(request.dataset_version_id),
                "workflow_id": request.workflow_id,
            }
        )
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
            source_dataset_sha256=version.content_sha256,
            created_by=tenant.user_id,
        )
        body = _research_job_response(job).model_dump(mode="json")
        try:
            created, replayed = store.create_idempotent(
                tenant.workspace_id,
                job,
                idempotency_key,
                fingerprint,
                body,
            )
        except ValueError as exc:
            if "idempotency key reused" in str(exc):
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            raise
        if replayed:
            return JSONResponse(
                status_code=202, content=_research_job_response(created).model_dump(mode="json")
            )
        jobs_created_total.inc()
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
            jobs_failed_total.inc()
            raise RuntimeError("research job queue unavailable") from exc
        return JSONResponse(status_code=202, content=body)

    @app.get("/v1/research-runs/{job_id}", response_model=ResearchJobResponse, tags=["research"])
    @require_permission(Resource.JOB, Action.READ)
    def get_research_run(
        job_id: UUID, tenant: TenantContext = Depends(current_tenant)
    ) -> ResearchJobResponse:
        job = store.get(tenant.workspace_id, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="research run not found")
        return _research_job_response(job)

    return app


app = create_app()

__all__ = ["AuthProvider", "app", "create_app"]
