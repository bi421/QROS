"""Supabase-backed persistence for tenant-scoped research jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from researchos.saas.contracts import ResearchJob, ResearchJobStatus
from researchos.saas.store import ResearchJobStore


class SupabaseResearchJobStore(ResearchJobStore):
    """Persist research jobs in ``public.research_run`` with tenant scoping."""

    def __init__(self, supabase_client: Any) -> None:
        self._client = supabase_client

    @staticmethod
    def _row_to_job(row: dict[str, Any]) -> ResearchJob:
        return ResearchJob(
            id=UUID(str(row["id"])),
            workspace_id=UUID(str(row["workspace_id"])),
            dataset_id=str(row["dataset_version_id"]),
            workflow_id=str(row["workflow_id"]),
            status=ResearchJobStatus(str(row["status"])),
            created_by=UUID(str(row["created_by"])) if row.get("created_by") else None,
        )

    def create(self, job: ResearchJob) -> ResearchJob:
        try:
            dataset_version_id = UUID(job.dataset_id)
        except ValueError as exc:
            raise ValueError("Supabase research jobs require a dataset version UUID") from exc
        if job.created_by is None:
            raise ValueError("Supabase research jobs require created_by")

        result = (
            self._client.table("research_run")
            .insert(
                {
                    "id": str(job.id),
                    "workspace_id": str(job.workspace_id),
                    "dataset_version_id": str(dataset_version_id),
                    "workflow_id": job.workflow_id,
                    "status": job.status.value,
                    "created_by": str(job.created_by),
                }
            )
            .select("id,workspace_id,dataset_version_id,workflow_id,status,created_by")
            .execute()
        )
        rows = result.data or []
        if len(rows) != 1:
            raise RuntimeError("Supabase research job insert returned no unique row")
        return self._row_to_job(rows[0])

    def get(self, workspace_id: UUID, job_id: UUID) -> ResearchJob | None:
        result = (
            self._client.table("research_run")
            .select("id,workspace_id,dataset_version_id,workflow_id,status,created_by")
            .eq("workspace_id", str(workspace_id))
            .eq("id", str(job_id))
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return self._row_to_job(rows[0]) if rows else None

    def count_active(self, workspace_id: UUID) -> int:
        result = (
            self._client.table("research_run")
            .select("id", count="exact", head=True)
            .eq("workspace_id", str(workspace_id))
            .in_("status", [ResearchJobStatus.QUEUED.value, ResearchJobStatus.RUNNING.value])
            .execute()
        )
        return int(result.count or 0)

    def count_monthly(self, workspace_id: UUID) -> int:
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        result = (
            self._client.table("research_run")
            .select("id", count="exact", head=True)
            .eq("workspace_id", str(workspace_id))
            .gte("created_at", month_start.isoformat())
            .execute()
        )
        return int(result.count or 0)

    def transition(
        self,
        workspace_id: UUID,
        job_id: UUID,
        expected: ResearchJobStatus,
        target: ResearchJobStatus,
    ) -> ResearchJob:
        result = (
            self._client.table("research_run")
            .update({"status": target.value})
            .eq("workspace_id", str(workspace_id))
            .eq("id", str(job_id))
            .eq("status", expected.value)
            .select("id,workspace_id,dataset_version_id,workflow_id,status,created_by")
            .execute()
        )
        rows = result.data or []
        if not rows:
            raise ValueError(
                f"invalid or missing research job transition: {expected.value} -> {target.value}"
            )
        if len(rows) != 1:
            raise RuntimeError("Supabase research job transition was not unique")
        return self._row_to_job(rows[0])


__all__ = ["SupabaseResearchJobStore"]
