"""Canonical role/resource/action authorization contract for the QROS SaaS API."""

from __future__ import annotations

import contextvars
import inspect
from enum import Enum
from functools import wraps
from typing import Any, Callable, ParamSpec, TypeVar
from uuid import uuid4

from fastapi import HTTPException, Request, status

from researchos.saas.contracts import TenantContext, WorkspaceRole

P = ParamSpec("P")
R = TypeVar("R")

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "qros_request_id", default=None
)


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    RESEARCHER = "researcher"
    VIEWER = "viewer"
    BILLING_ADMIN = "billing"


class Resource(str, Enum):
    WORKSPACE = "workspace"
    DATASET = "dataset"
    DATASET_VERSION = "dataset_version"
    JOB = "job"
    CLAIM = "claim"
    PLAN = "plan"
    EVIDENCE = "evidence"
    FINDING = "finding"
    BILLING = "billing"


class Action(str, Enum):
    CREATE = "create"
    READ = "read"
    LIST = "list"
    UPDATE = "update"
    DELETE = "delete"


ALL = frozenset(Action)
READ = frozenset({Action.READ, Action.LIST})
WRITE = frozenset({Action.CREATE, Action.READ, Action.LIST, Action.UPDATE})
MUTATE = frozenset({Action.CREATE, Action.READ, Action.LIST, Action.UPDATE, Action.DELETE})

# Single executable source of truth for docs and route coverage.
POLICY: dict[Role, dict[Resource, frozenset[Action]]] = {
    Role.OWNER: {resource: MUTATE for resource in Resource},
    Role.ADMIN: {
        Resource.WORKSPACE: frozenset({Action.READ, Action.LIST, Action.UPDATE}),
        Resource.DATASET: MUTATE,
        Resource.DATASET_VERSION: MUTATE,
        Resource.JOB: MUTATE,
        Resource.CLAIM: WRITE,
        Resource.PLAN: WRITE,
        Resource.EVIDENCE: READ,
        Resource.FINDING: WRITE,
        Resource.BILLING: frozenset({Action.READ, Action.LIST, Action.UPDATE}),
    },
    Role.RESEARCHER: {
        Resource.WORKSPACE: READ,
        Resource.DATASET: WRITE,
        Resource.DATASET_VERSION: WRITE,
        Resource.JOB: WRITE,
        Resource.CLAIM: WRITE,
        Resource.PLAN: WRITE,
        Resource.EVIDENCE: READ,
        Resource.FINDING: WRITE,
        Resource.BILLING: frozenset(),
    },
    Role.VIEWER: {resource: READ for resource in Resource},
    Role.BILLING_ADMIN: {
        Resource.WORKSPACE: READ,
        Resource.DATASET: READ,
        Resource.DATASET_VERSION: READ,
        Resource.JOB: READ,
        Resource.CLAIM: READ,
        Resource.PLAN: READ,
        Resource.EVIDENCE: READ,
        Resource.FINDING: READ,
        Resource.BILLING: WRITE,
    },
}

RESOURCE_ALIASES = {
    "research-run": Resource.JOB.value,
    "research_claim": Resource.CLAIM.value,
    "research-claim": Resource.CLAIM.value,
    "dataset-version": Resource.DATASET_VERSION.value,
}


def set_request_id(request_id: str | None) -> contextvars.Token[str | None]:
    return _request_id.set(request_id)


def reset_request_id(token: contextvars.Token[str | None]) -> None:
    _request_id.reset(token)


def current_request_id() -> str:
    return _request_id.get() or str(uuid4())


def _resource(value: Resource | str) -> Resource:
    raw = value.value if isinstance(value, Resource) else value.strip().lower()
    raw = RESOURCE_ALIASES.get(raw, raw)
    try:
        return Resource(raw)
    except ValueError as exc:
        raise ValueError(f"unknown authorization resource: {value}") from exc


def canonical_resource(value: Resource | str) -> str:
    return _resource(value).value


def _action(value: Action | str) -> Action:
    raw = value.value if isinstance(value, Action) else value.strip().lower()
    try:
        return Action(raw)
    except ValueError as exc:
        raise ValueError(f"unknown authorization action: {value}") from exc


def role_from_tenant(tenant: TenantContext) -> Role:
    if isinstance(tenant.role, Role):
        return tenant.role
    mapping = {
        WorkspaceRole.OWNER: Role.OWNER,
        WorkspaceRole.ADMIN: Role.ADMIN,
        WorkspaceRole.RESEARCHER: Role.RESEARCHER,
        WorkspaceRole.VIEWER: Role.VIEWER,
        WorkspaceRole.BILLING: Role.BILLING_ADMIN,
    }
    try:
        return mapping[tenant.role]
    except KeyError as exc:
        raise ValueError(f"unsupported tenant role: {tenant.role}") from exc


def is_allowed(role: Role | WorkspaceRole, resource: Resource | str, action: Action | str) -> bool:
    normalized_role = (
        role
        if isinstance(role, Role)
        else Role.BILLING_ADMIN if role == WorkspaceRole.BILLING
        else Role(role.value)
    )
    return _action(action) in POLICY[normalized_role][_resource(resource)]


def _tenant_from_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> TenantContext | None:
    for value in (*args, *kwargs.values()):
        if isinstance(value, TenantContext):
            return value
    return None


def _request_from_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Request | None:
    for value in (*args, *kwargs.values()):
        if isinstance(value, Request):
            return value
    return None


def _check(
    tenant: TenantContext | None,
    resource: Resource,
    action: Action,
    service_principal: bool,
    request: Request | None,
) -> None:
    if service_principal:
        return
    request_id = (
        str(getattr(request.state, "request_id", "") or "")
        if request is not None
        else current_request_id()
    ) or current_request_id()
    if tenant is None or not is_allowed(tenant.role, resource, action):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": f"permission denied: {resource.value}:{action.value}",
                "request_id": request_id,
            },
        )


def require_permission(
    resource: Resource | str,
    action: Action | str,
    *,
    service_principal: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Enforce a server-resolved TenantContext role at the HTTP boundary."""

    normalized_resource = _resource(resource)
    normalized_action = _action(action)

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                _check(
                    _tenant_from_call(args, kwargs),
                    normalized_resource,
                    normalized_action,
                    service_principal,
                    _request_from_call(args, kwargs),
                )
                return await func(*args, **kwargs)  # type: ignore[misc]
            return async_wrapper  # type: ignore[return-value]

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            _check(
                _tenant_from_call(args, kwargs),
                normalized_resource,
                normalized_action,
                service_principal,
                _request_from_call(args, kwargs),
            )
            return func(*args, **kwargs)

        return wrapper

    return decorator


__all__ = [
    "Action",
    "POLICY",
    "Resource",
    "Role",
    "canonical_resource",
    "current_request_id",
    "is_allowed",
    "require_permission",
    "reset_request_id",
    "role_from_tenant",
    "set_request_id",
]
