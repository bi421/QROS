"""Role-based authorization policy for the QROS SaaS HTTP boundary."""

from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable, ParamSpec, TypeVar

from fastapi import HTTPException, status

from researchos.saas.contracts import TenantContext, WorkspaceRole

P = ParamSpec("P")
R = TypeVar("R")

RESOURCES = ("dataset", "job", "evidence", "finding", "billing", "workspace")
ACTIONS = ("create", "read", "list", "update", "delete")

# False means forbidden. This is the executable source of truth for AUTHZ_MATRIX.md.
POLICY: dict[WorkspaceRole, dict[str, dict[str, bool]]] = {
    WorkspaceRole.OWNER: {
        resource: {action: True for action in ACTIONS} for resource in RESOURCES
    },
    WorkspaceRole.ADMIN: {
        "dataset": {"create": True, "read": True, "list": True, "update": True, "delete": True},
        "job": {"create": True, "read": True, "list": True, "update": True, "delete": True},
        "evidence": {"create": False, "read": True, "list": True, "update": False, "delete": False},
        "finding": {"create": True, "read": True, "list": True, "update": False, "delete": False},
        "billing": {"create": False, "read": True, "list": True, "update": True, "delete": False},
        "workspace": {"create": False, "read": True, "list": True, "update": True, "delete": False},
    },
    WorkspaceRole.RESEARCHER: {
        "dataset": {"create": True, "read": True, "list": True, "update": True, "delete": False},
        "job": {"create": True, "read": True, "list": True, "update": False, "delete": False},
        "evidence": {"create": False, "read": True, "list": True, "update": False, "delete": False},
        "finding": {"create": True, "read": True, "list": True, "update": False, "delete": False},
        "billing": {"create": False, "read": False, "list": False, "update": False, "delete": False},
        "workspace": {"create": False, "read": True, "list": True, "update": False, "delete": False},
    },
    WorkspaceRole.VIEWER: {
        resource: {
            action: action in {"read", "list"}
            for action in ACTIONS
        }
        for resource in RESOURCES
    },
    WorkspaceRole.BILLING: {
        "dataset": {"create": False, "read": True, "list": True, "update": False, "delete": False},
        "job": {"create": False, "read": True, "list": True, "update": False, "delete": False},
        "evidence": {"create": False, "read": True, "list": True, "update": False, "delete": False},
        "finding": {"create": False, "read": True, "list": True, "update": False, "delete": False},
        "billing": {"create": True, "read": True, "list": True, "update": True, "delete": False},
        "workspace": {"create": False, "read": True, "list": True, "update": False, "delete": False},
    },
}

_RESOURCE_ALIASES = {
    "research-run": "job",
    "research-claim": "job",
}


def canonical_resource(resource: str) -> str:
    value = resource.strip().lower()
    return _RESOURCE_ALIASES.get(value, value)


def is_allowed(role: WorkspaceRole, resource: str, action: str) -> bool:
    resource = canonical_resource(resource)
    action = action.strip().lower()
    if resource not in RESOURCES or action not in ACTIONS:
        raise ValueError(f"unknown authorization capability: {resource}:{action}")
    return POLICY[role][resource][action]


def require_permission(
    resource: str,
    action: str,
    *,
    service_principal: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator enforcing the server-resolved TenantContext role.

    Every decorated tenant route must receive a TenantContext from its JWT
    authentication dependency. The decorator never reads role/workspace data
    from request payloads or client headers.
    """

    canonical = canonical_resource(resource)
    normalized_action = action.strip().lower()
    if canonical not in RESOURCES or normalized_action not in ACTIONS:
        raise ValueError(f"unknown authorization capability: {resource}:{action}")

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                tenant = _tenant_from_call(kwargs)
                _check(tenant, canonical, normalized_action, service_principal)
                return await func(*args, **kwargs)  # type: ignore[misc]
            return async_wrapper  # type: ignore[return-value]

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            tenant = _tenant_from_call(kwargs)
            _check(tenant, canonical, normalized_action, service_principal)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def _tenant_from_call(kwargs: dict[str, Any]) -> TenantContext | None:
    for value in kwargs.values():
        if isinstance(value, TenantContext):
            return value
    return None


def _check(
    tenant: TenantContext | None,
    resource: str,
    action: str,
    service_principal: bool,
) -> None:
    if service_principal:
        return
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="authorization context is missing",
        )
    if not is_allowed(tenant.role, resource, action):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"permission denied: {resource}:{action}",
        )


__all__ = [
    "ACTIONS",
    "POLICY",
    "RESOURCES",
    "canonical_resource",
    "is_allowed",
    "require_permission",
]
