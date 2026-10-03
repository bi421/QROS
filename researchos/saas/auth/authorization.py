"""Backward-compatible import surface for the canonical authorization contract."""

from researchos.saas.auth.permissions import (
    Action,
    POLICY,
    Resource,
    Role,
    canonical_resource,
    is_allowed,
    require_permission,
)

ACTIONS = tuple(action.value for action in Action)
RESOURCES = tuple(resource.value for resource in Resource)

__all__ = [
    "ACTIONS",
    "POLICY",
    "RESOURCES",
    "canonical_resource",
    "is_allowed",
    "require_permission",
    "Action",
    "Resource",
    "Role",
]
