"""Secure HTTP boundary for the QROS SaaS MVP."""

from __future__ import annotations

from typing import Callable, Protocol, cast
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
    APIRouter,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from researchos.saas.api_middleware import RequestContextMiddleware
from researchos.saas.onboarding import ONBOARDING_HTML, ONBOARDING_JS
from researchos.saas.observability import (
    StructuredRequestObserver,
    actor_user_id_var,
    configure_logging,
    jobs_created_total,
    jobs_failed_total,
    observe_error,
    tenant_id_var,
    configure_tracing,
)
from researchos.saas.auth.permissions import Action, Resource, require_permission

from researchos.research_core.contracts import FROZEN_XAUUSD_M1_WORKFLOW
from researchos.saas.contracts import (
    DEFAULT_USAGE_POLICIES,
    Plan,
    ResearchJob,
    ResearchJobStatus,
    TenantContext,
    WorkspaceRole,
)
from researchos.saas.claim_api import ResearchClaimStore, register_research_claim_routes
from researchos.saas.evidence_api import ResearchEvidenceStore, register_research_evidence_routes
from researchos.saas.finding_api import (
    InMemoryResearchFindingStore,
    ResearchFindingStore,
    register_research_finding_routes,
)
from researchos.saas.validation_api import (
    InMemoryResearchValidationStore,
    ResearchValidationStore,
    register_research_validation_routes,
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
from researchos.saas.persistence import (
    DEFAULT_RETENTION_DAYS,
    InMemoryTenantPersistence,
    TenantPersistence,
    RetentionConfig,
    TenantPersistenceError,
)
from researchos.saas.pagination import (paginate, validate_filter_tenant_id, validate_filter_keys, parse_list_query, PaginationParameterError, pagination_envelope)
from researchos.saas.research_report import build_research_report
from researchos.saas.workspace import (
    WorkspaceProvisioningConflict,
    WorkspaceProvisioner,
)
from researchos.saas.billing import (
    BillingEventConflict,
    BillingEventStore,
    BillingSignatureError,
    BillingProvider,
    BillingProviderError,
    parse_billing_event,
    verify_hmac_signature,
    verify_stripe_signature,
    EntitlementStore,
    InMemoryEntitlementStore,
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
    if isinstance(detail, dict) and isinstance(detail.get("code"), str):
        code = str(detail["code"])
        message = str(detail.get("message", "request failed"))
    else:
        message = detail if isinstance(detail, str) else "request failed"
        code = (
            detail
            if isinstance(detail, str) and detail.startswith("INVALID_")
            else _error_code(status_code)
        )
    return {
        "code": code,
        "message": message,
        "request_id": getattr(request.state, "request_id", None),
        "correlation_id": request.headers.get("X-Correlation-ID")
        or getattr(request.state, "request_id", None),
    }


def _safe_validation_details(exc: RequestValidationError) -> list[dict[str, object]]:
    """Return client-safe validation details without echoing submitted values."""
    return [
        {
            "loc": error.get("loc", ()),
            "msg": str(error.get("msg", "validation error")),
            "type": str(error.get("type", "validation_error")),
        }
        for error in exc.errors()
    ]


def _validate_dataset_name(name: str) -> str:
    """Reject path-like dataset names before they cross any storage boundary."""
    normalized = name.strip()
    if not normalized or "/" in normalized or "\\" in normalized or ".." in normalized:
        raise HTTPException(status_code=400, detail="INVALID_PATH")
    return normalized


class AuthProvider(Protocol):
    """Authenticate a request and resolve its authorized workspace."""

    def authenticate(self, authorization: str | None) -> TenantContext: ...
    def authenticate_user(self, authorization: str | None) -> UUID: ...


class UnconfiguredAuthProvider:
    """Fail-closed default; production must install a real identity provider."""

    def authenticate(self, authorization: str | None) -> TenantContext:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SaaS authentication provider is not configured",
        )

    def authenticate_user(self, authorization: str | None) -> UUID:
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


class BillingCheckoutRequest(BaseModel):
    plan: Plan


class BillingActionResponse(BaseModel):
    url: str


class WorkspaceCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1, max_length=256)


class WorkspaceProvisioningResponse(BaseModel):
    workspace_id: UUID
    role: str
    plan: str


class PaginationResponse(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class PageResponse(BaseModel):
    data: list[object]
    pagination: PaginationResponse
    request_id: str


class DeletionReceiptResponse(BaseModel):
    workspace_id: UUID
    deleted_at: str
    scheduled_purge_date: str
    retention_days: int
    receipt_id: UUID


class DatasetResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    created_by: UUID
    version: DatasetVersion | None

class DatasetPageResponse(BaseModel):
    items: list[DatasetResponse]
    total: int
    limit: int
    offset: int
    has_more: bool



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
    entitlement_store: EntitlementStore | None = None,
    plan_rate_limiters: dict[Plan, RateLimiter] | None = None,
    claim_store: ResearchClaimStore | None = None,
    evidence_store: ResearchEvidenceStore | None = None,
    validation_store: ResearchValidationStore | None = None,
    finding_store: ResearchFindingStore | None = None,
    billing_webhook_secret: str | None = None,
    billing_provider: BillingProvider | None = None,
    rate_limiter: RateLimiter | None = None,
    metrics_token: str | None = None,
    readiness_probe: Callable[[], None] | None = None,
    workspace_provisioner: WorkspaceProvisioner | None = None,
    tenant_persistence: TenantPersistence | None = None,
    supabase_url: str | None = None,
    supabase_publishable_key: str | None = None,
    billing_plan_by_price_id: dict[str, str] | None = None,
) -> FastAPI:
    """Build the SaaS API with explicit dependency injection for testing/deployment."""

    configure_tracing()
    auth = auth_provider or UnconfiguredAuthProvider()
    store = job_store or InMemoryResearchJobStore()
    datasets = dataset_store or InMemoryDatasetStore()
    storage = dataset_storage or InMemoryDatasetStorage()
    queue = job_queue or InMemoryResearchJobQueue()
    limiter = rate_limiter or FixedWindowRateLimiter(limit=120, window_seconds=60)
    billing = billing_store
    entitlements: EntitlementStore = entitlement_store or InMemoryEntitlementStore()
    plan_limiters = plan_rate_limiters or {}
    workspaces = workspace_provisioner
    persistence = tenant_persistence or InMemoryTenantPersistence()
    retention = RetentionConfig(DEFAULT_RETENTION_DAYS)
    app = FastAPI(
        title="QROS SaaS API",
        version="1.0.0",
        description="Multi-tenant delivery API for auditable financial research.",
    )
    app.add_middleware(RequestContextMiddleware)
    app.state.observability = StructuredRequestObserver()

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        observe_error(
            severity="warning",
            error_code=_error_code(exc.status_code),
            error=exc,
            metadata={
                "method": request.method,
                "path": request.url.path,
                "status_code": exc.status_code,
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content=_error_payload(request, exc.status_code, exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        observe_error(
            severity="warning",
            error_code="validation_error",
            error=exc,
            metadata={
                "method": request.method,
                "path": request.url.path,
                "status_code": 400,
            },
        )
        payload = {
            "code": "validation_error",
            "message": "Request validation failed",
            "request_id": getattr(request.state, "request_id", None),
            "correlation_id": request.headers.get("X-Correlation-ID")
            or getattr(request.state, "request_id", None),
        }
        return JSONResponse(status_code=400, content=payload)

    @app.exception_handler(Exception)
    async def internal_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        observe_error(
            severity="error",
            error_code="internal_error",
            error=exc,
            metadata={
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
            },
        )
        logger.exception("unhandled request exception request_id=%s", request_id)
        return JSONResponse(
            status_code=500,
            headers={REQUEST_ID_HEADER: request_id} if request_id else None,
            content=_error_payload(request, 500, "Internal error"),
        )

    def current_tenant(authorization: str | None = Header(default=None)) -> TenantContext:
        tenant = auth.authenticate(authorization)
        tenant_id_var.set(str(tenant.workspace_id))
        actor_user_id_var.set(str(tenant.user_id))
        return tenant

    def require_role(tenant: TenantContext, *allowed: WorkspaceRole) -> None:
        if tenant.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="workspace role is not authorized",
            )

    def require_active_workspace(tenant: TenantContext) -> None:
        try:
            deleted = persistence.is_workspace_deleted(tenant.workspace_id)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="workspace lifecycle state unavailable",
            ) from exc
        if deleted:
            raise HTTPException(status_code=410, detail="workspace is deleted")

    def require_rate_limit(tenant: TenantContext) -> None:
        principal = hashlib.sha256(f"workspace:{tenant.workspace_id}".encode()).hexdigest()
        effective_limiter = plan_limiters.get(tenant.plan, limiter)
        try:
            allowed = effective_limiter.allow(principal)
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
        except PermissionError as exc:
            app.state.observability.metrics.inc_tenant_isolation_violation()
            raise HTTPException(status_code=403, detail="tenant storage authorization failed") from exc
        except ValueError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise RuntimeError("dataset version persistence failed") from exc

    @app.get("/onboarding", include_in_schema=False, response_class=HTMLResponse)
    def onboarding() -> HTMLResponse:
        return HTMLResponse(ONBOARDING_HTML)

    @app.get("/onboarding/app.js", include_in_schema=False, response_class=Response)
    def onboarding_app_js() -> Response:
        return Response(ONBOARDING_JS, media_type="application/javascript")

    @app.get("/onboarding/config", include_in_schema=False, tags=["identity"])
    def onboarding_config() -> dict[str, str]:
        if not supabase_url or not supabase_publishable_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="customer onboarding is not configured",
            )
        return {
            "supabase_url": supabase_url.rstrip("/"),
            "supabase_publishable_key": supabase_publishable_key,
        }

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False, tags=["system"])
    def metrics(request: Request) -> Response:
        if metrics_token is None:
            raise HTTPException(status_code=503, detail="metrics endpoint is not configured")
        if request.headers.get("X-Metrics-Token") != metrics_token:
            raise HTTPException(status_code=404, detail="not found")
        observer = request.app.state.observability
        if not isinstance(observer, StructuredRequestObserver):
            raise HTTPException(status_code=503, detail="observability is not configured")
        observer.observe(
            request_id=getattr(request.state, "request_id", ""),
            method=request.method,
            path=request.url.path,
            status_code=200,
            duration_ms=0.0,
        )
        return Response(
            content=observer.metrics.prometheus_text(),
            media_type="text/plain; version=0.0.4",
        )

    @app.get("/readyz", tags=["system"])
    def readyz() -> dict[str, str]:
        if store is None or datasets is None or storage is None or queue is None:
            raise HTTPException(status_code=503, detail="SaaS persistence is not configured")
        if readiness_probe is not None:
            try:
                readiness_probe()
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail="SaaS dependency readiness check failed",
                ) from exc
        return {"status": "ready"}

    @app.post(
        "/v1/billing/checkout",
        response_model=BillingActionResponse,
        status_code=201,
        tags=["billing"],
    )
    def billing_checkout(
        request: BillingCheckoutRequest,
        tenant: TenantContext = Depends(current_tenant),
    ) -> BillingActionResponse:
        require_active_workspace(tenant)
        require_role(tenant, WorkspaceRole.OWNER, WorkspaceRole.BILLING_ADMIN)
        if billing_provider is None:
            raise HTTPException(status_code=503, detail="billing checkout is not configured")
        if request.plan is Plan.FREE:
            raise HTTPException(status_code=400, detail="free plan does not require checkout")
        if request.plan is tenant.plan:
            raise HTTPException(status_code=409, detail="workspace is already on the requested plan")
        try:
            url = billing_provider.create_checkout_session(
                workspace_id=tenant.workspace_id,
                plan=request.plan.value,
            )
        except BillingProviderError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return BillingActionResponse(url=url)

    @app.post(
        "/v1/billing/portal",
        response_model=BillingActionResponse,
        status_code=201,
        tags=["billing"],
    )
    def billing_portal(
        tenant: TenantContext = Depends(current_tenant),
    ) -> BillingActionResponse:
        require_active_workspace(tenant)
        require_role(tenant, WorkspaceRole.OWNER, WorkspaceRole.BILLING_ADMIN)
        if billing_provider is None:
            raise HTTPException(status_code=503, detail="billing portal is not configured")
        try:
            url = billing_provider.create_portal_session(workspace_id=tenant.workspace_id)
        except BillingProviderError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return BillingActionResponse(url=url)

    @app.post("/v1/billing/webhook", status_code=200, tags=["billing"])
    @require_permission("billing", "create", service_principal=True)
    async def billing_webhook(
        request: Request,
        x_billing_signature: str | None = Header(default=None, alias="X-Billing-Signature"),
        stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
        x_billing_provider: str | None = Header(default=None, alias="X-Billing-Provider"),
    ) -> dict[str, str]:
        if billing is None or not billing_webhook_secret:
            raise HTTPException(status_code=503, detail="billing webhook is not configured")
        signature = stripe_signature or x_billing_signature
        if not signature or not x_billing_provider:
            raise HTTPException(
                status_code=400, detail="billing signature and provider are required"
            )
        provider = x_billing_provider.strip().lower()
        if provider not in {"stripe", "hmac"}:
            raise HTTPException(status_code=400, detail="unsupported billing provider")
        payload = await request.body()
        try:
            if signature.startswith("t="):
                verify_stripe_signature(payload, signature, billing_webhook_secret)
            else:
                verify_hmac_signature(payload, signature, billing_webhook_secret)
            event = parse_billing_event(payload, plan_by_price_id=billing_plan_by_price_id)
        except BillingSignatureError as exc:
            raise HTTPException(
                status_code=401, detail="invalid billing webhook signature"
            ) from exc
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="invalid billing event") from exc
        payload_sha256 = hashlib.sha256(payload).hexdigest()
        try:
            processed = billing.process(event, provider, payload_sha256)
        except BillingEventConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise RuntimeError("billing event processing failed") from exc
        return {"status": "processed" if processed else "replayed"}

    @app.post(
        "/v1/workspaces",
        response_model=WorkspaceProvisioningResponse,
        status_code=201,
        tags=["identity"],
    )
    def provision_workspace(
        request: WorkspaceCreateRequest,
        authorization: str | None = Header(default=None),
    ) -> WorkspaceProvisioningResponse:
        if workspaces is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="workspace provisioning is not configured",
            )
        user_id = auth.authenticate_user(authorization)
        try:
            provisioned = workspaces.provision(user_id, request.name)
        except WorkspaceProvisioningConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="workspace provisioning unavailable",
            ) from exc
        return WorkspaceProvisioningResponse(
            workspace_id=provisioned.workspace_id,
            role=provisioned.role.value,
            plan=provisioned.plan.value,
        )

    @app.get("/v1/me", response_model=dict[str, str], tags=["identity"])
    @require_permission("workspace", "read")
    def me(tenant: TenantContext = Depends(current_tenant)) -> dict[str, str]:
        return {
            "user_id": str(tenant.user_id),
            "workspace_id": str(tenant.workspace_id),
            "plan": tenant.plan.value,
        }

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
        request: Request,
        page: str = "1",
        page_size: str = "20",
        sort_by: str = "created_at",
        sort_order: str = "desc",
        name: str | None = None,
        tenant_filter: str | None = Query(default=None, alias="filter[tenant_id]"),
        tenant: TenantContext = Depends(current_tenant),
    ) -> PageResponse:
        require_active_workspace(tenant)
        try:
            if request is not None:
                validate_filter_keys(
                    {key.removeprefix("filter[").removesuffix("]"): value for key, value in request.query_params.items() if key.startswith("filter[")},
                    allowed=frozenset({"tenant_id"}),
                )
            query = parse_list_query(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
                tenant_id=tenant_filter,
                allowed_sort_fields=frozenset({"created_at", "name"}),
            )
            if name is not None and not 1 <= len(name.strip()) <= 256:
                raise PaginationParameterError(
                    "name filter must be between 1 and 256 characters"
                )
            if tenant_filter is not None and tenant_filter != str(tenant.workspace_id):
                rows, total = [], 0
            else:
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
        return cast(
            PageResponse,
            PageResponse.model_validate(
                pagination_envelope(
                    data=[item.model_dump(mode="json") for item in items],
                    page=query.page,
                    page_size=query.page_size,
                    total=total,
                    request_id=request.state.request_id if request is not None else "",
                )
            ),
        )

    @app.get("/v1/research-runs", response_model=PageResponse, tags=["research"])
    @require_permission(Resource.JOB, Action.LIST)
    def list_research_runs(
        request: Request,
        page: str = "1",
        page_size: str = "20",
        sort_by: str = "created_at",
        sort_order: str = "desc",
        filter_status: str | None = Query(default=None, alias="filter[status]"),
        filter_workflow_id: str | None = Query(default=None, alias="filter[workflow_id]"),
        tenant: TenantContext = Depends(current_tenant),
    ) -> PageResponse:
        try:
            validate_filter_keys(
                {
                    key.removeprefix("filter[").removesuffix("]"): value
                    for key, value in request.query_params.items()
                    if key.startswith("filter[")
                },
                allowed=frozenset({"status", "workflow_id"}),
            )
            query = parse_list_query(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
                allowed_sort_fields=frozenset({"created_at", "status", "workflow_id"}),
            )
            status_filter: ResearchJobStatus | None = None
            if filter_status is not None:
                try:
                    status_filter = ResearchJobStatus(filter_status)
                except ValueError as exc:
                    raise PaginationParameterError("invalid status filter") from exc
            workflow_filter = (
                filter_workflow_id.strip() if filter_workflow_id is not None else None
            )
            if workflow_filter == "":
                raise PaginationParameterError("workflow_id filter must not be empty")
            rows, total = store.list(
                tenant.workspace_id,
                limit=query.page_size,
                offset=query.offset,
                status=status_filter,
                workflow_id=workflow_filter,
                sort_by=query.sort_by,
                sort_order=query.sort_order,
            )
        except PaginationParameterError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        return cast(
            PageResponse,
            PageResponse.model_validate(
                pagination_envelope(
                    data=[
                        _research_job_response(job).model_dump(mode="json")
                        for job in rows
                    ],
                    page=query.page,
                    page_size=query.page_size,
                    total=total,
                    request_id=request.state.request_id,
                )
            ),
        )

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
            entitlement = entitlements.get(tenant.workspace_id, tenant.plan.value)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="entitlement service unavailable") from exc
        if entitlement.max_datasets > 0 and datasets.count_datasets(tenant.workspace_id) >= entitlement.max_datasets:
            raise HTTPException(
                status_code=402,
                detail={"code": "ENTITLEMENT_EXCEEDED", "message": "dataset entitlement exceeded", "upgrade_url": "https://qros.ai/upgrade"},
            )
        policy = DEFAULT_USAGE_POLICIES[tenant.plan]
        persisted_dataset = None
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

    @app.get(
        "/v1/datasets/{dataset_id}/versions/{version_id}/download",
        response_model=dict[str, str],
        tags=["datasets"],
    )
    @require_permission(Resource.DATASET_VERSION, Action.READ)
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
            url = storage.create_signed_download_url(version.storage_path, 3600)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="dataset object not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="dataset download service unavailable") from exc
        return {"url": url, "expires_in": "3600"}

    @app.post(
        "/v1/research-runs", response_model=ResearchJobResponse, status_code=202, tags=["research"]
    )
    @require_permission(Resource.JOB, Action.CREATE)
    def create_research_run(
        payload: ResearchCreateRequest,
        request: Request,
        tenant: TenantContext = Depends(current_tenant),
        idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    ) -> Response:
        require_rate_limit(tenant)
        if payload.workflow_id != FROZEN_XAUUSD_M1_WORKFLOW:
            raise HTTPException(status_code=400, detail="unsupported workflow")
        if not idempotency_key:
            raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise HTTPException(status_code=400, detail="invalid Idempotency-Key")
        fingerprint = request_fingerprint(
            {
                "dataset_version_id": str(payload.dataset_version_id),
                "workflow_id": payload.workflow_id,
            }
        )
        try:
            entitlement = entitlements.get(tenant.workspace_id, tenant.plan.value)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="entitlement service unavailable") from exc
        policy = DEFAULT_USAGE_POLICIES[tenant.plan]
        if not entitlement.allows_jobs(store.count_monthly(tenant.workspace_id)):
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "ENTITLEMENT_EXCEEDED",
                    "message": "monthly job entitlement exceeded",
                    "upgrade_url": "https://qros.ai/upgrade",
                },
            )
        if not policy.allows_concurrency(store.count_active(tenant.workspace_id)):
            raise HTTPException(status_code=429, detail="concurrent research run limit reached")
        version = datasets.get_version(tenant.workspace_id, payload.dataset_version_id)
        if version is None:
            raise HTTPException(status_code=404, detail="dataset version not found")

        job = ResearchJob(
            id=uuid4(),
            workspace_id=tenant.workspace_id,
            dataset_version_id=version.id,
            workflow_id=payload.workflow_id,
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
                queue.enqueue(
                    tenant.workspace_id,
                    created.id,
                    request_id=getattr(request.state, "request_id", None),
                )
            except Exception:
                pass
            jobs_failed_total.inc()
            raise RuntimeError("research job queue unavailable") from exc
        return JSONResponse(status_code=202, content=body)

    @app.get("/v1/research-runs/{job_id}/logs", response_model=list[dict[str, object]], tags=["research"])
    @require_permission("job", "read")
    def get_research_run_logs(
        job_id: UUID,
        page: int = Query(default=1),
        page_size: int = Query(default=20),
        tenant: TenantContext = Depends(current_tenant),
    ) -> list[dict[str, object]]:
        if page < 1 or page_size < 1 or page_size > 100:
            raise HTTPException(status_code=400, detail="INVALID_PAGINATION")
        if store.get(tenant.workspace_id, job_id) is None:
            raise HTTPException(status_code=404, detail="research run not found")
        return store.logs(tenant.workspace_id, job_id)

    @app.get("/v1/research-runs/{job_id}/result", tags=["research"])
    @require_permission(Resource.JOB, Action.READ)
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
    @require_permission(Resource.JOB, Action.READ)
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
    @require_permission(Resource.JOB, Action.READ)
    def get_research_run(
        job_id: UUID, tenant: TenantContext = Depends(current_tenant)
    ) -> ResearchJobResponse:
        job = store.get(tenant.workspace_id, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="research run not found")
        return _research_job_response(job)

    claim_router = APIRouter()
    register_research_claim_routes(
        claim_router,
        tenant_dependency=current_tenant,
        claim_store=claim_store,
    )
    app.include_router(claim_router)

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

__all__ = ["AuthProvider", "app", "create_app"]
