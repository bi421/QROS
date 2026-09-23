from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from researchos.saas.auth.permissions import Action, Resource, authorize, is_allowed
from researchos.saas.contracts import Plan, TenantContext, WorkspaceRole


@pytest.mark.parametrize("role", list(WorkspaceRole))
def test_permission_matrix_has_explicit_default_behavior(role: WorkspaceRole) -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO, role=role)
    for resource in Resource:
        for action in Action:
            allowed = is_allowed(role, resource, action)
            if allowed:
                authorize(context, resource, action)
            else:
                with pytest.raises(HTTPException) as exc:
                    authorize(context, resource, action)
                assert exc.value.status_code == 403
                assert exc.value.detail == "FORBIDDEN"


def test_viewer_cannot_create_jobs() -> None:
    context = TenantContext(uuid4(), uuid4(), Plan.PRO, role=WorkspaceRole.VIEWER)
    with pytest.raises(HTTPException) as exc:
        authorize(context, Resource.JOB, Action.CREATE)
    assert exc.value.status_code == 403
