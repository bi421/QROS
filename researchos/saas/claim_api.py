"""Customer-facing tenant-scoped Research Claim API routes."""

from __future__ import annotations

import hashlib
from typing import Any, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from researchos.claims.claim import ResearchClaim, ResearchClaimType, ResearchPlan
from researchos.saas.auth.authorization import require_permission
from researchos.saas.contracts import TenantContext, WorkspaceRole
from researchos.saas.pagination import PaginationParameterError, pagination_envelope, parse_list_query, validate_filter_keys


class ResearchClaimStore(Protocol):
    def save(self, workspace_id: UUID, claim: ResearchClaim) -> ResearchClaim:
        ...

    def get(self, workspace_id: UUID, claim_id: str) -> ResearchClaim | None:
        ...

    def list(
        self, workspace_id: UUID, *, limit: int = 100, offset: int = 0, sort_by: str = "created_at", sort_order: str = "desc", status: str | None = None
    ) -> tuple[list[ResearchClaim], int]:
        ...


class ResearchClaimCreateRequest(BaseModel):
    statement: str = Field(min_length=1, max_length=10_000)
    claim_type: ResearchClaimType = ResearchClaimType.EMPIRICAL
    target_population: str = Field(default="", max_length=2_000)
    instrument: str = Field(default="", max_length=512)
    horizon: str = Field(default="", max_length=512)
    timestamp_policy: str = Field(default="", max_length=2_000)
    economic_rationale: str = Field(default="", max_length=5_000)
    falsification_conditions: list[str] = Field(default_factory=list, max_length=100)
    primary_metrics: list[str] = Field(default_factory=list, max_length=100)
    minimum_evidence_requirements: list[str] = Field(default_factory=list, max_length=100)
    research_id: str | None = Field(default=None, max_length=256)
    ontology_tags: list[str] = Field(default_factory=list, max_length=100)


class ResearchPlanLockRequest(BaseModel):
    hypothesis: str = Field(min_length=1, max_length=10_000)
    sample_definition: str = Field(min_length=1, max_length=10_000)
    features: list[str] = Field(min_length=1, max_length=100)
    labels: list[str] = Field(default_factory=list, max_length=100)
    train_validation_test: str = Field(min_length=1, max_length=2_000)
    exclusions: list[str] = Field(default_factory=list, max_length=100)
    costs_slippage: str = Field(min_length=1, max_length=5_000)
    statistical_tests: list[str] = Field(default_factory=list, max_length=100)
    metrics: list[str] = Field(min_length=1, max_length=100)
    stopping_rules: list[str] = Field(default_factory=list, max_length=100)
    multiple_testing_policy: str = Field(min_length=1, max_length=2_000)
    replication_policy: str = Field(min_length=1, max_length=2_000)


class ResearchClaimResponse(BaseModel):
    id: str
    workspace_id: str
    statement: str
    claim_type: str
    evidence_state: str
    version: int
    parent_claim_id: str | None
    research_id: str | None
    creator: str
    claim_hash: str
    plan_hash: str | None
    is_plan_locked: bool


class ResearchClaimPageResponse(BaseModel):
    data: list[ResearchClaimResponse]
    pagination: dict[str, int]
    request_id: str


def _response(claim: ResearchClaim) -> ResearchClaimResponse:
    return ResearchClaimResponse(
        id=claim.id,
        workspace_id=claim.workspace_id,
        statement=claim.statement,
        claim_type=claim.claim_type.value,
        evidence_state=claim.evidence_state.value,
        version=claim.version,
        parent_claim_id=claim.parent_claim_id,
        research_id=claim.research_id,
        creator=claim.creator,
        claim_hash=claim.claim_hash,
        plan_hash=claim.plan_hash,
        is_plan_locked=claim.is_plan_locked,
    )


def _stable_claim_id(tenant: TenantContext, request: ResearchClaimCreateRequest) -> str:
    """Make repeated identical creates by one actor naturally idempotent.

    The creator is included deliberately: two members may submit the same
    statement without one member overwriting the other's claim.
    """
    canonical = request.model_dump(mode="json")
    canonical["creator"] = str(tenant.user_id)
    canonical["workspace_id"] = str(tenant.workspace_id)
    encoded = repr(sorted(canonical.items())).encode("utf-8")
    return hashlib.sha256(b"qros:research-claim:" + encoded).hexdigest()


def register_research_claim_routes(
    router: APIRouter | FastAPI,
    *,
    tenant_dependency: Any,
    claim_store: ResearchClaimStore | None,
) -> None:
    """Attach v1 claim routes without exposing an unconfigured persistence fallback."""

    def require_store() -> ResearchClaimStore:
        if claim_store is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="research claim persistence is not configured",
            )
        return claim_store

    def require_write_role(context: TenantContext) -> None:
        if context.role not in (
            WorkspaceRole.OWNER,
            WorkspaceRole.ADMIN,
            WorkspaceRole.RESEARCHER,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="workspace role is not authorized",
            )

    @router.post(
        "/v1/research-claims",
        response_model=ResearchClaimResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["research-claims"],
    )
    @require_permission("claim", "create")
    def create_research_claim(
        request: ResearchClaimCreateRequest,
        context: TenantContext = Depends(tenant_dependency),
    ) -> ResearchClaimResponse:
        require_write_role(context)
        store = require_store()
        try:
            claim = ResearchClaim(
                statement=request.statement,
                claim_type=request.claim_type,
                target_population=request.target_population,
                instrument=request.instrument,
                horizon=request.horizon,
                timestamp_policy=request.timestamp_policy,
                economic_rationale=request.economic_rationale,
                falsification_conditions=request.falsification_conditions,
                primary_metrics=request.primary_metrics,
                minimum_evidence_requirements=request.minimum_evidence_requirements,
                creator=str(context.user_id),
                workspace_id=str(context.workspace_id),
                research_id=request.research_id,
                ontology_tags=request.ontology_tags,
                id=_stable_claim_id(context, request),
                version=1,
            )
            persisted = store.save(context.workspace_id, claim)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="research claim persistence failed",
            ) from exc
        return _response(persisted)

    @router.post(
        "/v1/research-claims/{claim_id}/plan-lock",
        response_model=ResearchClaimResponse,
        tags=["research-claims"],
    )
    @require_permission("plan", "update")
    def lock_research_claim_plan(
        claim_id: str,
        request: ResearchPlanLockRequest,
        context: TenantContext = Depends(tenant_dependency),
    ) -> ResearchClaimResponse:
        require_write_role(context)
        if not claim_id.strip() or len(claim_id) > 256:
            raise HTTPException(status_code=422, detail="invalid claim id")
        store = require_store()
        try:
            claim = store.get(context.workspace_id, claim_id)
            if claim is None:
                raise HTTPException(status_code=404, detail="research claim not found")
            plan = ResearchPlan(
                hypothesis=request.hypothesis,
                sample_definition=request.sample_definition,
                features=tuple(request.features),
                labels=tuple(request.labels),
                train_validation_test=request.train_validation_test,
                exclusions=tuple(request.exclusions),
                costs_slippage=request.costs_slippage,
                statistical_tests=tuple(request.statistical_tests),
                metrics=tuple(request.metrics),
                stopping_rules=tuple(request.stopping_rules),
                multiple_testing_policy=request.multiple_testing_policy,
                replication_policy=request.replication_policy,
            )
            claim.lock_plan(plan)
            persisted = store.save(context.workspace_id, claim)
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="research claim plan-lock persistence failed",
            ) from exc
        return _response(persisted)

    @router.get(
        "/v1/research-claims/{claim_id}",
        response_model=ResearchClaimResponse,
        tags=["research-claims"],
    )
    @require_permission("claim", "read")
    def get_research_claim(
        claim_id: str,
        context: TenantContext = Depends(tenant_dependency),
    ) -> ResearchClaimResponse:
        if not claim_id.strip() or len(claim_id) > 256:
            raise HTTPException(status_code=422, detail="invalid claim id")
        store = require_store()
        try:
            claim = store.get(context.workspace_id, claim_id)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="research claim persistence unavailable",
            ) from exc
        if claim is None:
            raise HTTPException(status_code=404, detail="research claim not found")
        return _response(claim)

    @router.get(
        "/v1/research-claims",
        response_model=ResearchClaimPageResponse,
        tags=["research-claims"],
    )
    @require_permission("claim", "list")
    def list_research_claims(
        page: str = "1",
        page_size: str = "20",
        sort_by: str = "created_at",
        sort_order: str = "desc",
        status_filter: str | None = Query(default=None, alias="filter[status]"),
        tenant_filter: str | None = Query(default=None, alias="filter[tenant_id]"),
        context: TenantContext = Depends(tenant_dependency),
    ) -> ResearchClaimPageResponse:
        try:
            validate_filter_keys(
                {key.removeprefix("filter[").removesuffix("]"): value for key, value in request.query_params.items() if key.startswith("filter[")},
                allowed=frozenset({"status", "tenant_id"}),
            )
            query = parse_list_query(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
                status=status_filter,
                tenant_id=tenant_filter,
                allowed_sort_fields=frozenset({"created_at", "status", "statement"}),
            )
        except PaginationParameterError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        store = require_store()
        if tenant_filter is not None and tenant_filter != str(context.workspace_id):
            claims, total = [], 0
        else:
            try:
                claims, total = store.list(
                    context.workspace_id,
                    limit=query.page_size,
                    offset=query.offset,
                    sort_by=query.sort_by,
                    sort_order=query.sort_order,
                    status=query.status,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "INVALID_SORT" if "sort" in str(exc) else "INVALID_FILTER", "message": str(exc)},
                ) from exc
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="research claim persistence unavailable",
                ) from exc
        items = [_response(claim) for claim in claims]
        return ResearchClaimPageResponse.model_validate(
            pagination_envelope(
                data=[item.model_dump(mode="json") for item in items],
                page=query.page,
                page_size=query.page_size,
                total=total,
                request_id=request.state.request_id,
            )
        )


__all__ = [
    "ResearchClaimCreateRequest",
    "ResearchClaimPageResponse",
    "ResearchClaimResponse",
    "ResearchPlanLockRequest",
    "ResearchClaimStore",
    "register_research_claim_routes",
]
