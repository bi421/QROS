"""Secure HTTP boundary for the QROS SaaS MVP."""

from __future__ import annotations

from typing import Protocol, Sequence
from uuid import UUID, uuid4
import hashlib
import hmac
import json
import time

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response, StreamingResponse

from researchos.research_core.contracts import FROZEN_XAUUSD_M1_WORKFLOW
from researchos.saas.contracts import DEFAULT_USAGE_POLICIES, PageRequest, ResearchJob, ResearchJobStatus, TenantContext, WorkspaceRole
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
from researchos.saas.claim_api import ResearchClaimStore, register_research_claim_routes
from researchos.saas.evidence_api import ResearchEvidenceStore, register_research_evidence_routes
from researchos.saas.validation_api import InMemoryResearchValidationStore, ResearchValidationStore, register_research_validation_routes
from researchos.saas.finding_api import InMemoryResearchFindingStore, register_research_finding_routes
from researchos.saas.pagination import PaginationParameterError, pagination_envelope, parse_list_query
from researchos.saas.research_report import build_research_report
from researchos.saas.observability import StructuredRequestObserver, observe_request
from researchos.saas.auth.authorization import require_permission
from researchos.saas.persistence import (
    DEFAULT_RETENTION_DAYS,
    InMemoryTenantPersistence,
    RetentionConfig,
    TenantPersistence,
    TenantPersistenceError,
)
from researchos.saas.billing import (
    BillingEventConflict,
    BillingEventStore,
    BillingSignatureError,
    parse_billing_event,
    verify_hmac_signature,
)

REQUEST_ID_HEADER = "X-Request-ID"
WORKSPACE_HEADER = "X-Workspace-ID"
IDEMPOTENCY_HEADER = "Idempotency-Key"
MAX_REQUEST_ID_LENGTH = 128


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


def _error_payload(request: Request, status_code: int, detail: object) -> dict[str, object]:
    detail_code = detail.get("code") if isinstance(detail, dict) else None
    detail_message = detail.get("message") if isinstance(detail, dict) else None
    message = (
        str(detail_message)
        if detail_message is not None
        else detail
        if isinstance(detail, str)
        else "request failed"
    )
    return {
        "code": str(detail_code) if detail_code else _error_code(status_code),
        "message": message,
        "request_id": getattr(request.state, "request_id", None),
        "correlation_id": getattr(request.state, "request_id", None),
    }


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Attach one bounded correlation ID to every HTTP request and response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        supplied = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = supplied[:MAX_REQUEST_ID_LENGTH] if supplied else str(uuid4())
        request_id = "".join(char if ord(char) >= 32 and ord(char) != 127 else "-" for char in request_id)
        request.state.request_id = request_id
        request.state.correlation_id = request_id
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            observer = getattr(request.app.state, "observability", None)
            if isinstance(observer, StructuredRequestObserver):
                route = request.scope.get("route")
                path = getattr(route, "path", request.url.path)
                observe_request(
                    observer,
                    request_id=request_id,
                    method=request.method,
                    path=path,
                    status_code=500,
                    started_at=started_at,
                )
            raise
        response.headers[REQUEST_ID_HEADER] = request_id
        observer = getattr(request.app.state, "observability", None)
        if isinstance(observer, StructuredRequestObserver):
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            observe_request(
                observer,
                request_id=request_id,
                method=request.method,
                path=path,
                status_code=response.status_code,
                started_at=started_at,
            )
        return response


class AuthProvider(Protocol):
    """Authenticate a request and resolve its authorized workspace."""

    def authenticate(
        self,
        authorization: str | None,
        requested_workspace_id: UUID | None = None,
    ) -> TenantContext:
        ...


class UnconfiguredAuthProvider:
    """Fail-closed default; production must install a real identity provider."""

    def authenticate(
        self,
        authorization: str | None,
        requested_workspace_id: UUID | None = None,
    ) -> TenantContext:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SaaS authentication provider is not configured",
        )


class ResearchCreateRequest(BaseModel):
    dataset_version_id: UUID
    workflow_id: str = Field(default=FROZEN_XAUUSD_M1_WORKFLOW, min_length=1, max_length=128)
    claim_id: str | None = Field(default=None, min_length=1, max_length=256)
    plan_hash: str | None = Field(default=None, min_length=64, max_length=64)


class PaginationResponse(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class PageResponse(BaseModel):
    data: list[object]
    pagination: PaginationResponse

class DeletionReceiptResponse(BaseModel):
    workspace_id: UUID
    deleted_at: str
    scheduled_purge_date: str
    retention_days: int
    receipt_id: UUID


class ResearchJobResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    dataset_version_id: UUID
    workflow_id: str
    status: ResearchJobStatus
    claim_id: str | None = None
    plan_hash: str | None = None


class DatasetResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    created_by: UUID
    version: DatasetVersion | None


def _research_job_response(job: ResearchJob) -> ResearchJobResponse:
    """Serialize the domain dataclass explicitly at the HTTP boundary."""
    return ResearchJobResponse(
        id=job.id,
        workspace_id=job.workspace_id,
        dataset_version_id=job.dataset_version_id,
        workflow_id=job.workflow_id,
        status=job.status,
        claim_id=job.claim_id,
        plan_hash=job.plan_hash,
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
    metrics_token: str | None = None,
    rate_limiter: RateLimiter | None = None,
    claim_store: ResearchClaimStore | None = None,
    evidence_store: ResearchEvidenceStore | None = None,
    validation_store: ResearchValidationStore | None = None,
    finding_store=None,
    tenant_persistence: TenantPersistence | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> FastAPI:
    """Build the SaaS API with explicit dependency injection for testing/deployment."""

    auth = auth_provider or UnconfiguredAuthProvider()
    store = job_store or InMemoryResearchJobStore()
    datasets = dataset_store or InMemoryDatasetStore()
    storage = dataset_storage or InMemoryDatasetStorage()
    queue = job_queue or InMemoryResearchJobQueue()
    limiter = rate_limiter or FixedWindowRateLimiter(limit=120, window_seconds=60)
    billing = billing_store
    persistence = tenant_persistence or InMemoryTenantPersistence()
    retention = RetentionConfig(retention_days)
    app = FastAPI(
        title="QROS SaaS API",
        version="1.0.0",
        description="Multi-tenant delivery API for auditable financial research.",
    )
    app.add_middleware(RequestCorrelationMiddleware)
    app.state.observability = StructuredRequestObserver()

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content=_error_payload(request, exc.status_code, exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_payload(request, 422, exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        del exc
        return JSONResponse(
            status_code=500,
            content=_error_payload(request, 500, "internal server error"),
        )

    def current_tenant(
        authorization: str | None = Header(default=None),
        workspace_header: str | None = Header(default=None, alias=WORKSPACE_HEADER),
    ) -> TenantContext:
        requested_workspace_id: UUID | None = None
        if workspace_header is not None:
            try:
                requested_workspace_id = UUID(workspace_header.strip())
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="invalid X-Workspace-ID") from exc
        tenant = auth.authenticate(authorization, requested_workspace_id)
        if persistence.is_workspace_deleted(tenant.workspace_id):
            raise HTTPException(status_code=410, detail="workspace is deleted")
        return tenant

    def require_role(tenant: TenantContext, *allowed: WorkspaceRole) -> None:
        """Enforce server-resolved membership roles; never trust request data."""
        if tenant.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="workspace role is not authorized")

    def require_rate_limit(tenant: TenantContext) -> None:
        principal = hashlib.sha256(
            f"workspace:{tenant.workspace_id}".encode()
        ).hexdigest()
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
                    tenant.workspace_id,
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

    @app.get("/metrics", tags=["system"])
    def metrics(metrics_header: str | None = Header(default=None, alias="X-Metrics-Token")) -> Response:
        """Expose process metrics only when an explicit scrape credential is configured."""
        if not metrics_token:
            raise HTTPException(status_code=503, detail="metrics endpoint is not configured")
        if not metrics_header or not hmac.compare_digest(metrics_header, metrics_token):
            raise HTTPException(status_code=404, detail="metrics endpoint not found")
        observer = app.state.observability
        return Response(content=observer.metrics.prometheus_text(), media_type="text/plain; version=0.0.4")

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["system"])
    def readyz() -> dict[str, str]:
        if store is None or datasets is None or storage is None or queue is None:
            raise HTTPException(status_code=503, detail="SaaS persistence is not configured")
        return {"status": "ready"}

    @app.post("/v1/billing/webhook", status_code=200, tags=["billing"])
    @require_permission("billing", "create", service_principal=True)
    async def billing_webhook(
        request: Request,
        x_billing_signature: str | None = Header(default=None, alias="X-Billing-Signature"),
        x_billing_provider: str | None = Header(default=None, alias="X-Billing-Provider"),
    ) -> dict[str, str]:
        if billing is None or not billing_webhook_secret:
            raise HTTPException(status_code=503, detail="billing webhook is not configured")
        if not x_billing_signature or not x_billing_provider:
            raise HTTPException(status_code=400, detail="billing signature and provider are required")
        payload = await request.body()
        try:
            verify_hmac_signature(payload, x_billing_signature, billing_webhook_secret)
            event = parse_billing_event(payload)
        except BillingSignatureError as exc:
            raise HTTPException(status_code=401, detail="invalid billing webhook signature") from exc
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="invalid billing event") from exc
        payload_sha256 = hashlib.sha256(payload).hexdigest()
        try:
            processed = billing.process(event, x_billing_provider.strip()[:64], payload_sha256)
        except BillingEventConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="billing event processing failed") from exc
        return {"status": "processed" if processed else "replayed"}

    @app.get("/v1/me", response_model=dict[str, str], tags=["identity"])
    @require_permission("workspace", "read")
    def me(tenant: TenantContext = Depends(current_tenant)) -> dict[str, str]:
        return {"user_id": str(tenant.user_id), "workspace_id": str(tenant.workspace_id), "plan": tenant.plan.value}

    @app.delete("/v1/workspaces/{workspace_id}", response_model=DeletionReceiptResponse, tags=["workspace"])
    @require_permission("workspace", "delete")
    def delete_workspace(
        workspace_id: UUID,
        tenant: TenantContext = Depends(current_tenant),
    ) -> DeletionReceiptResponse:
        if workspace_id != tenant.workspace_id:
            raise HTTPException(status_code=404, detail="workspace not found")
        require_role(tenant, WorkspaceRole.OWNER, WorkspaceRole.ADMIN)
        try:
            receipt = persistence.soft_delete_workspace(
                workspace_id,
                retention=retention,
            )
        except TenantPersistenceError as exc:
            raise HTTPException(status_code=503, detail="workspace deletion unavailable") from exc
        return DeletionReceiptResponse(
            workspace_id=receipt.workspace_id,
            deleted_at=receipt.deleted_at.isoformat(),
            scheduled_purge_date=receipt.scheduled_purge_at.isoformat(),
            retention_days=receipt.retention_days,
            receipt_id=receipt.receipt_id,
        )

    @app.get("/v1/workspaces/{workspace_id}/export", tags=["workspace"])
    @require_permission("workspace", "read")
    def export_workspace(
        workspace_id: UUID,
        tenant: TenantContext = Depends(current_tenant),
    ) -> Response:
        if workspace_id != tenant.workspace_id:
            raise HTTPException(status_code=404, detail="workspace not found")
        try:
            archive = persistence.export_workspace(workspace_id)
        except TenantPersistenceError as exc:
            raise HTTPException(status_code=503, detail="workspace export unavailable") from exc
        return StreamingResponse(
            iter((archive,)),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="qros-workspace-{workspace_id}.zip"',
            },
        )

    @app.get("/v1/datasets", response_model=PageResponse, tags=["datasets"])
    @require_permission("dataset", "list")
    def list_datasets(
        page: str = "1",
        page_size: str = "20",
        sort_by: str = "created_at",
        sort_order: str = "desc",
        name: str | None = None,
        tenant: TenantContext = Depends(current_tenant),
    ) -> PageResponse:
        try:
            query = parse_list_query(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
                allowed_sort_fields=frozenset({"created_at", "name"}),
            )
            if name is not None and not 1 <= len(name.strip()) <= 256:
                raise PaginationParameterError(
                    "name filter must be between 1 and 256 characters"
                )
            rows, total = datasets.list_datasets(
                tenant.workspace_id,
                limit=query.page_size,
                offset=query.offset,
                name_filter=name,
                sort_by=query.sort_by,
                sort_order=query.sort_order,
            )
        except PaginationParameterError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        items = [
            DatasetResponse(
                id=row.id, workspace_id=row.workspace_id, name=row.name,
                created_by=row.created_by,
                version=sorted(
                    datasets.list_versions(tenant.workspace_id, row.id),
                    key=lambda item: item.version_no,
                )[-1] if datasets.list_versions(tenant.workspace_id, row.id) else None,
            )
            for row in rows
        ]
        return PageResponse.model_validate(
            pagination_envelope(
                data=[item.model_dump(mode="json") for item in items],
                page=query.page,
                page_size=query.page_size,
                total=total,
            )
        )

    @app.post("/v1/datasets", response_model=DatasetResponse, status_code=201, tags=["datasets"])
    @require_permission("dataset", "create")
    def upload_dataset(
        name: str = Form(..., min_length=1, max_length=256),
        file: UploadFile = File(...),
        tenant: TenantContext = Depends(current_tenant),
    ) -> DatasetResponse:
        require_role(tenant, WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.RESEARCHER)
        dataset = Dataset(id=uuid4(), workspace_id=tenant.workspace_id, name=name.strip(), created_by=tenant.user_id)
        policy = DEFAULT_USAGE_POLICIES[tenant.plan]
        try:
            digest, size = stream_sha256(file.file, policy.max_dataset_bytes)
            if not policy.allows_dataset(size):
                raise ValueError("dataset exceeds plan upload limit")
            storage_path = storage_path_for(tenant.workspace_id, dataset.id, digest)
            storage.put(storage_path, file.file)
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
    @require_permission("dataset", "update")
    def upload_dataset_version(
        dataset_id: UUID,
        file: UploadFile = File(...),
        tenant: TenantContext = Depends(current_tenant),
    ) -> DatasetVersion:
        require_role(tenant, WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.RESEARCHER)
        if datasets.get_dataset(tenant.workspace_id, dataset_id) is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        return persist_version(dataset_id=dataset_id, tenant=tenant, file=file)

    @app.get("/v1/datasets/{dataset_id}/versions", response_model=list[DatasetVersion], tags=["datasets"])
    @require_permission("dataset", "list")
    def list_dataset_versions(
        dataset_id: UUID,
        tenant: TenantContext = Depends(current_tenant),
    ) -> list[DatasetVersion]:
        return datasets.list_versions(tenant.workspace_id, dataset_id)

    @app.get("/v1/datasets/{dataset_id}/versions/{version_id}/download", response_model=dict[str, str], tags=["datasets"])
    @require_permission("dataset", "read")
    def create_dataset_download_url(
        dataset_id: UUID,
        version_id: UUID,
        tenant: TenantContext = Depends(current_tenant),
    ) -> dict[str, str]:
        """Authorize tenant ownership before issuing a short-lived private URL."""
        version = datasets.get_version(tenant.workspace_id, version_id)
        if version is None or version.dataset_id != dataset_id:
            raise HTTPException(status_code=404, detail="dataset version not found")
        try:
            url = storage.create_signed_download_url(version.storage_path, 300)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="dataset object not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="dataset download service unavailable") from exc
        return {"url": url, "expires_in": "300"}

    @app.post("/v1/research-runs", response_model=ResearchJobResponse, status_code=202, tags=["research"])
    @require_permission("job", "create")
    def create_research_run(
        request: ResearchCreateRequest,
        tenant: TenantContext = Depends(current_tenant),
        idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    ) -> Response:
        require_role(tenant, WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.RESEARCHER)
        require_rate_limit(tenant)
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
            "claim_id": request.claim_id,
            "plan_hash": request.plan_hash,
        })
        policy = DEFAULT_USAGE_POLICIES[tenant.plan]
        if not policy.allows_monthly_runs(store.count_monthly(tenant.workspace_id)):
            raise HTTPException(status_code=402, detail="research run limit reached")
        if not policy.allows_concurrency(store.count_active(tenant.workspace_id)):
            raise HTTPException(status_code=429, detail="concurrent research run limit reached")
        version = datasets.get_version(tenant.workspace_id, request.dataset_version_id)
        if version is None:
            raise HTTPException(status_code=404, detail="dataset version not found")
        if (request.claim_id is None) != (request.plan_hash is None):
            raise HTTPException(status_code=422, detail="claim_id and plan_hash are required together")
        if request.claim_id is not None:
            if claim_store is None:
                raise HTTPException(status_code=503, detail="research claim persistence is not configured")
            claim = claim_store.get(tenant.workspace_id, request.claim_id)
            if claim is None:
                raise HTTPException(status_code=404, detail="research claim not found")
            if not claim.is_plan_locked or claim.plan_hash != request.plan_hash:
                raise HTTPException(status_code=409, detail="research claim plan is not locked or plan_hash does not match")

        job = ResearchJob(
            id=uuid4(),
            workspace_id=tenant.workspace_id,
            dataset_version_id=version.id,
            workflow_id=request.workflow_id,
            status=ResearchJobStatus.QUEUED,
            source_dataset_sha256=version.content_sha256,
            created_by=tenant.user_id,
            claim_id=request.claim_id,
            plan_hash=request.plan_hash,
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
            return JSONResponse(status_code=202, content=_research_job_response(created).model_dump(mode="json"))
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
        return JSONResponse(status_code=202, content=_research_job_response(created).model_dump(mode="json"))

    @app.get("/v1/research-runs", response_model=PageResponse, tags=["research"])
    @require_permission("job", "list")
    def list_research_runs(
        page: str = "1",
        page_size: str = "20",
        sort_by: str = "created_at",
        sort_order: str = "desc",
        status_filter: str | None = Query(default=None, alias="filter[status]"),
        workflow_id: str | None = None,
        tenant: TenantContext = Depends(current_tenant),
    ) -> PageResponse:
        try:
            query = parse_list_query(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
                status=status_filter,
                allowed_sort_fields=frozenset({"created_at", "status", "workflow_id"}),
            )
            normalized_status = (
                "succeeded" if query.status == "completed" else query.status
            )
            status_value = (
                ResearchJobStatus(normalized_status)
                if normalized_status is not None
                else None
            )
        except (PaginationParameterError, ValueError) as exc:
            code = exc.code if isinstance(exc, PaginationParameterError) else "INVALID_FILTER"
            raise HTTPException(
                status_code=400,
                detail={"code": code, "message": str(exc)},
            ) from exc
        if workflow_id is not None and not 1 <= len(workflow_id) <= 128:
            raise HTTPException(status_code=400, detail={"code": "INVALID_FILTER", "message": "workflow_id must be between 1 and 128 characters"})
        jobs, total = store.list(
            tenant.workspace_id,
            limit=query.page_size,
            offset=query.offset,
            status=status_value,
            workflow_id=workflow_id,
            sort_by=query.sort_by,
            sort_order=query.sort_order,
        )
        items = [_research_job_response(job).model_dump(mode="json") for job in jobs]
        return PageResponse.model_validate(
            pagination_envelope(
                data=items,
                page=query.page,
                page_size=query.page_size,
                total=total,
            )
        )

    @app.get("/v1/research-runs/{job_id}/logs", response_model=list[dict[str, object]], tags=["research"])
    @require_permission("job", "read")
    def get_research_run_logs(
        job_id: UUID,
        tenant: TenantContext = Depends(current_tenant),
    ) -> list[dict[str, object]]:
        if store.get(tenant.workspace_id, job_id) is None:
            raise HTTPException(status_code=404, detail="research run not found")
        return store.logs(tenant.workspace_id, job_id)

    @app.get("/v1/research-runs/{job_id}/result", tags=["research"])
    @require_permission("job", "read")
    def get_research_run_result(
        job_id: UUID,
        tenant: TenantContext = Depends(current_tenant),
    ) -> dict[str, object]:
        record = store.get_result(tenant.workspace_id, job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="research result not found")
        return {
            "workspace_id": str(record.workspace_id),
            "research_run_id": str(record.research_run_id),
            "claim_id": str(record.claim_id) if record.claim_id else None,
            "plan_hash": record.plan_hash,
            "source_dataset_sha256": record.source_dataset_sha256,
            "status": record.status,
            "manifest_sha256": record.manifest_sha256,
            "artifacts": [
                {
                    "artifact_id": artifact.artifact_id,
                    "kind": artifact.kind,
                    "content_sha256": artifact.content_sha256,
                }
                for artifact in record.artifacts
            ],
            "failures": list(record.failures),
        }

    @app.get("/v1/research-runs/{job_id}/report", tags=["research"])
    @require_permission("job", "read")
    def get_research_run_report(
        job_id: UUID,
        tenant: TenantContext = Depends(current_tenant),
    ) -> dict[str, object]:
        record = store.get_result(tenant.workspace_id, job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="research result not found")
        if evidence_store is None:
            raise HTTPException(
                status_code=503,
                detail="research evidence persistence is not configured",
            )
        try:
            evidence = evidence_store.list_for_run(tenant.workspace_id, job_id)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="research evidence persistence unavailable",
            ) from exc
        finding = finding_store.get(tenant.workspace_id, job_id) if finding_store is not None else None
        report = build_research_report(record, evidence, finding)
        return {
            "schema": report.schema,
            "workspace_id": str(report.workspace_id),
            "research_run_id": str(report.research_run_id),
            "status": report.status,
            "source_dataset_sha256": report.source_dataset_sha256,
            "manifest_sha256": report.manifest_sha256,
            "report_sha256": report.report_sha256,
            "finding_sha256": report.finding_sha256,
            "markdown": report.markdown,
        }

    @app.get("/v1/research-runs/{job_id}", response_model=ResearchJobResponse, tags=["research"])
    @require_permission("job", "read")
    def get_research_run(job_id: UUID, tenant: TenantContext = Depends(current_tenant)) -> ResearchJobResponse:
        job = store.get(tenant.workspace_id, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="research run not found")
        return _research_job_response(job)

    register_research_claim_routes(
        app,
        tenant_dependency=current_tenant,
        claim_store=claim_store,
    )

    register_research_evidence_routes(
        app,
        tenant_dependency=current_tenant,
        evidence_store=evidence_store,
    )

    effective_validation_store = validation_store or InMemoryResearchValidationStore()
    register_research_validation_routes(
        app,
        tenant_dependency=current_tenant,
        validation_store=effective_validation_store,
        job_store=store,
    )

    register_research_finding_routes(
        app,
        tenant_dependency=current_tenant,
        finding_store=finding_store or InMemoryResearchFindingStore(),
        validation_store=effective_validation_store,
    )

    original_openapi = app.openapi

    def _custom_openapi() -> dict[str, object]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = original_openapi()
        components = schema.setdefault("components", {})
        schemas = components.setdefault("schemas", {})
        schemas["ErrorResponse"] = {
            "type": "object",
            "required": ["code", "message", "request_id", "correlation_id"],
            "properties": {
                "code": {"type": "string", "example": "not_found"},
                "message": {"type": "string", "example": "research run not found"},
                "request_id": {"type": "string", "example": "01JQROSREQUEST123"},
                "correlation_id": {"type": "string", "example": "01JQROSREQUEST123"},
            },
        }
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                responses = operation.setdefault("responses", {})
                for code in ("400", "401", "403", "404", "409", "413", "422", "429", "500", "503"):
                    response = responses.setdefault(code, {"description": "Structured API error"})
                    response.setdefault("content", {})["application/json"] = {
                        "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                        "example": {
                            "code": _error_code(int(code)),
                            "message": "request failed",
                            "request_id": "01JQROSREQUEST123",
                            "correlation_id": "01JQROSREQUEST123",
                        },
                    }
                for response in responses.values():
                    if isinstance(response, dict):
                        headers = response.setdefault("headers", {})
                        headers["X-Request-ID"] = {
                            "description": "Bounded request/correlation identifier.",
                            "schema": {"type": "string", "maxLength": MAX_REQUEST_ID_LENGTH},
                            "example": "01JQROSREQUEST123",
                        }
        app.openapi_schema = schema
        return schema

    app.openapi = _custom_openapi
    return app


app = create_app()

__all__ = ["AuthProvider", "RequestCorrelationMiddleware", "app", "create_app"]
