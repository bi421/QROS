"""Server-side workspace membership resolver for Supabase Postgres.

Use a server-only Supabase client here. The service-role credential must never
be sent to a browser or accepted from a request.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from researchos.saas.contracts import Plan


class SupabaseWorkspaceMembershipResolver:
    """Resolve one active workspace membership and server-side subscription plan."""

    def __init__(self, supabase_client: Any) -> None:
        self._client = supabase_client

    def resolve(self, user_id: UUID, requested_workspace_id: UUID | None = None) -> tuple[UUID, Plan] | None:
        """Resolve an authorized workspace without silently choosing one.

        A user may belong to multiple workspaces. If the caller supplies a
        workspace, membership must match that exact workspace. If no workspace
        is supplied, resolution is only allowed when membership is unambiguous.
        """
        membership = (
            self._client.table("workspace_member")
            .select("workspace_id")
            .eq("user_id", str(user_id))
            .execute()
        )
        rows = membership.data or []
        if not rows:
            return None
        workspace_ids = {UUID(str(row["workspace_id"])) for row in rows}
        if requested_workspace_id is not None:
            if requested_workspace_id not in workspace_ids:
                return None
            workspace_id = requested_workspace_id
        elif len(workspace_ids) == 1:
            workspace_id = next(iter(workspace_ids))
        else:
            raise ValueError("workspace selection is required for multi-workspace users")
        subscription = (
            self._client.table("subscription")
            .select("plan,status")
            .eq("workspace_id", str(workspace_id))
            .limit(1)
            .execute()
        )
        subscriptions = subscription.data or []
        if not subscriptions:
            return workspace_id, Plan.FREE

        row = subscriptions[0]
        if row.get("status") not in {"active", "trialing"}:
            return workspace_id, Plan.FREE

        try:
            return workspace_id, Plan(str(row["plan"]))
        except (KeyError, ValueError) as exc:
            # Never downgrade malformed billing state to FREE. A bad
            # entitlement record must fail closed rather than grant access
            # under an unintended plan.
            raise RuntimeError("invalid active subscription entitlement") from exc


__all__ = ["SupabaseWorkspaceMembershipResolver"]
