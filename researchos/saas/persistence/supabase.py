"""Supabase service-role tenant lifecycle persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from researchos.saas.retention_reconciliation import DeletionOperationState, SupabaseDeletionOperationStore
from researchos.saas.persistence.tenant import (
    RetentionConfig,
    DeletionReceipt,
    TenantPersistenceError,
    build_export_zip,
)


class SupabaseTenantPersistence:
    """Server-only tenant deletion/export adapter.

    The service-role client is required because deletion is a privileged
    lifecycle operation and the SQL RPC owns the cross-table transaction.
    """

    _EXPORT_TABLES = (
        "workspace",
        "workspace_member",
        "subscription",
        "dataset",
        "research_run",
        "artifact",
        "evidence",
        "usage_event",
        "audit_log",
        "billing_event",
        "research_claim",
        "research_validation",
        "research_finding",
        "research_run_result",
        "research_run_artifact",
        "audit_event",
    )

    def __init__(self, supabase_client: Any) -> None:
        self._client = supabase_client
        self._operations = SupabaseDeletionOperationStore(supabase_client)

    def is_workspace_deleted(self, workspace_id: UUID) -> bool:
        result = (
            self._client.table("workspace")
            .select("deleted_at")
            .eq("id", str(workspace_id))
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return bool(rows and rows[0].get("deleted_at"))

    def soft_delete_workspace(
        self,
        workspace_id: UUID,
        *,
        retention: RetentionConfig | None = None,
        deleted_at: datetime | None = None,
    ) -> DeletionReceipt:
        policy = retention or RetentionConfig()
        when = deleted_at or datetime.now(timezone.utc)
        operation_id = f"workspace-delete-{workspace_id}"
        operation = self._operations.reserve(
            workspace_id,
            operation_id,
            "workspace",
            str(workspace_id),
        )
        if operation.state is DeletionOperationState.COMPLETED:
            result = self._client.rpc(
                "soft_delete_workspace",
                {
                    "p_workspace_id": str(workspace_id),
                    "p_deleted_at": when.isoformat(),
                    "p_retention_days": policy.retention_days,
                },
            ).execute()
        else:
            self._operations.transition(
                workspace_id,
                operation_id,
                "workspace",
                str(workspace_id),
                DeletionOperationState.DELETE_ATTEMPTED,
            )
            try:
                result = self._client.rpc(
                    "soft_delete_workspace",
                    {
                        "p_workspace_id": str(workspace_id),
                        "p_deleted_at": when.isoformat(),
                        "p_retention_days": policy.retention_days,
                    },
                ).execute()
            except Exception:
                self._operations.transition(
                    workspace_id,
                    operation_id,
                    "workspace",
                    str(workspace_id),
                    DeletionOperationState.RECONCILIATION_REQUIRED,
                )
                raise
            self._operations.transition(
                workspace_id,
                operation_id,
                "workspace",
                str(workspace_id),
                DeletionOperationState.COMPLETED,
            )
        rows = result.data or []
        if len(rows) != 1:
            raise TenantPersistenceError("workspace soft-delete returned no receipt")
        row = rows[0]
        return DeletionReceipt(
            workspace_id=UUID(str(row["workspace_id"])),
            deleted_at=datetime.fromisoformat(str(row["deleted_at"]).replace("Z", "+00:00")),
            scheduled_purge_at=datetime.fromisoformat(
                str(row["scheduled_purge_at"]).replace("Z", "+00:00")
            ),
            retention_days=int(row["retention_days"]),
            receipt_id=UUID(str(row["receipt_id"])),
        )

    def _rows(self, table: str, workspace_id: UUID) -> list[dict[str, Any]]:
        result = (
            self._client.table(table)
            .select("*")
            .eq("workspace_id", str(workspace_id))
            .execute()
        )
        return [dict(row) for row in (result.data or [])]

    def export_workspace(self, workspace_id: UUID) -> bytes:
        try:
            workspace_result = (
                self._client.table("workspace")
                .select("*")
                .eq("id", str(workspace_id))
                .limit(1)
                .execute()
            )
            rows = {
                table: self._rows(table, workspace_id)
                for table in self._EXPORT_TABLES
                if table not in {"workspace", "workspace_member", "subscription"}
            }
            rows["workspace"] = [dict(row) for row in (workspace_result.data or [])]
            for table in ("workspace_member", "subscription"):
                rows[table] = self._rows(table, workspace_id)
            dataset_ids = [str(row["id"]) for row in rows["dataset"]]
            if dataset_ids:
                versions = (
                    self._client.table("dataset_version")
                    .select("*")
                    .in_("dataset_id", dataset_ids)
                    .execute()
                )
                rows["dataset_version"] = [dict(row) for row in (versions.data or [])]
            else:
                rows["dataset_version"] = []

            return build_export_zip(
                workspace_id=workspace_id,
                datasets=rows["dataset"],
                jobs=rows["research_run"],
                evidence_envelopes=rows["evidence"],
                additional={
                    key: value
                    for key, value in rows.items()
                    if key not in {"dataset", "research_run", "evidence"}
                },
            )
        except Exception as exc:
            raise TenantPersistenceError("tenant export failed") from exc


__all__ = ["SupabaseTenantPersistence"]
