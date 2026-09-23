"""Role/resource/action authorization for SaaS routes."""
from __future__ import annotations
from enum import Enum
from functools import wraps
from typing import Callable, ParamSpec, TypeVar
from fastapi import HTTPException
from researchos.saas.contracts import TenantContext, WorkspaceRole

class Resource(str, Enum):
    WORKSPACE="workspace"; DATASET="dataset"; DATASET_VERSION="dataset_version"; JOB="job"; CLAIM="claim"; PLAN="plan"; EVIDENCE="evidence"; FINDING="finding"; BILLING="billing"
class Action(str, Enum):
    CREATE="create"; READ="read"; LIST="list"; UPDATE="update"; DELETE="delete"

_POLICY={role:set() for role in WorkspaceRole}
for action in Action:
    _POLICY[WorkspaceRole.OWNER].update((r,action) for r in Resource)
    _POLICY[WorkspaceRole.ADMIN].update((r,action) for r in Resource if r != Resource.BILLING)
_POLICY[WorkspaceRole.ADMIN].update({(Resource.BILLING,Action.READ),(Resource.BILLING,Action.LIST),(Resource.BILLING,Action.UPDATE)})
for resource in (Resource.DATASET,Resource.DATASET_VERSION,Resource.JOB,Resource.CLAIM,Resource.PLAN,Resource.EVIDENCE,Resource.FINDING):
    _POLICY[WorkspaceRole.RESEARCHER].update({(resource,Action.READ),(resource,Action.LIST),(resource,Action.CREATE),(resource,Action.UPDATE)})
for resource in Resource:
    _POLICY[WorkspaceRole.VIEWER].update({(resource,Action.READ),(resource,Action.LIST)})

def is_allowed(role: WorkspaceRole, resource: Resource, action: Action) -> bool:
    return (resource, action) in _POLICY.get(role, set())

def authorize(context: TenantContext, resource: Resource, action: Action) -> None:
    if not is_allowed(context.role, resource, action):
        raise HTTPException(status_code=403, detail="FORBIDDEN")

P=ParamSpec("P"); R=TypeVar("R")
def require_permission(resource: Resource, action: Action) -> Callable[[Callable[P,R]], Callable[P,R]]:
    def decorator(func: Callable[P,R]) -> Callable[P,R]:
        @wraps(func)
        def wrapped(*args:P.args,**kwargs:P.kwargs)->R:
            tenant=kwargs.get("tenant")
            if not isinstance(tenant,TenantContext):
                raise HTTPException(status_code=403, detail="FORBIDDEN")
            authorize(tenant,resource,action)
            return func(*args,**kwargs)
        return wrapped
    return decorator

__all__=["Action","Resource","authorize","is_allowed","require_permission"]
