"""Server-side workspace membership resolver for Supabase Postgres.

Use a server-only Supabase client here. The service-role credential must never
be sent to a browser or accepted from a request.
"""

from __future__ import annotations

from uuid import UUID

from researchos.saas.contracts import Plan


class SupabaseWorkspaceMembershipResolver:
    """Resolve one active workspace membership and server-side subscription plan."""

    def __init__(self, supabase_client) -> None:
        self._client = supabase_client

    def resolve(self, user_id: UUID) -> tuple[UUID, Plan] | None:
        membership = (
            self._client.table("workspace_member")
            .select("workspace_id")
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        )
        rows = membership.data or []
        if not rows:
            return None

        workspace_id = UUID(str(rows[0]["workspace_id"]))
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
        except (KeyError, ValueError):
            return workspace_id, Plan.FREE


__all__ = ["SupabaseWorkspaceMembershipResolver"]
