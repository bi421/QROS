"""Supabase-backed persistence for tenant-scoped research jobs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from researchos.saas.contracts import ResearchJob, ResearchJobStatus
from researchos.saas.store import ResearchJobStore, WorkerLease


class SupabaseResearchJobStore(ResearchJobStore):
    def __init__(self, supabase_client: Any) -> None:
        self._client = supabase_client

    @staticmethod
    def _row_to_job(row: dict[str, Any]) -> ResearchJob:
        return ResearchJob(
            id=UUID(str(row["id"])),
            workspace_id=UUID(str(row["workspace_id"])),
            dataset_version_id=UUID(str(row["dataset_version_id"])),
            workflow_id=str(row["workflow_id"]),
            status=ResearchJobStatus(str(row["status"])),
            created_by=(
                UUID(str(row["created_by"])) if row.get("created_by") else None
            ),
        )

    def create(self, job: ResearchJob) -> ResearchJob:
        if job.created_by is None:
            raise ValueError("Supabase research jobs require created_by")
        result = (
            self._client.table("research_run")
            .insert(
                {
                    "id": str(job.id),
                    "workspace_id": str(job.workspace_id),
                    "dataset_version_id": str(job.dataset_version_id),
                    "workflow_id": job.workflow_id,
                    "status": job.status.value,
                    "created_by": str(job.created_by),
                }
            )
            .select(
                "id,workspace_id,dataset_version_id,workflow_id,status,created_by"
            )
            .execute()
        )
        rows = result.data or []
        if len(rows) != 1:
            raise RuntimeError(
                "Supabase research job insert returned no unique row"
            )
        return self._row_to_job(rows[0])

    def get(
        self,
        workspace_id: UUID,
        job_id: UUID,
    ) -> ResearchJob | None:
        result = (
            self._client.table("research_run")
            .select(
                "id,workspace_id,dataset_version_id,workflow_id,status,created_by"
            )
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
            .in_("status", ["queued", "running"])
            .execute()
        )
        return int(result.count or 0)

    def count_monthly(self, workspace_id: UUID) -> int:
        now = datetime.now(timezone.utc)
        month_start = now.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        result = (
            self._client.table("research_run")
            .select("id", count="exact", head=True)
            .eq("workspace_id", str(workspace_id))
            .gte("created_at", month_start.isoformat())
            .execute()
        )
        return int(result.count or 0)

    def claim(
        self,
        workspace_id: UUID,
        job_id: UUID,
        owner: str,
        lease_seconds: int,
    ) -> WorkerLease:
        result = self._client.rpc(
            "claim_research_run",
            {
                "p_research_run_id": str(job_id),
                "p_workspace_id": str(workspace_id),
                "p_lease_owner": owner,
                "p_lease_seconds": lease_seconds,
            },
        ).execute()
        rows = result.data or []
        if len(rows) != 1:
            raise RuntimeError("research job is unavailable for claim")
        row = rows[0]
        return WorkerLease(
            self._row_to_job(row),
            UUID(str(row["lease_token"])),
        )

    def renew(
        self,
        workspace_id: UUID,
        job_id: UUID,
        lease_token: UUID,
        lease_seconds: int,
    ) -> WorkerLease:
        result = self._client.rpc(
            "renew_research_run",
            {
                "p_research_run_id": str(job_id),
                "p_workspace_id": str(workspace_id),
                "p_lease_token": str(lease_token),
                "p_lease_seconds": lease_seconds,
            },
        ).execute()
        rows = result.data or []
        if len(rows) != 1:
            raise RuntimeError("stale or invalid worker lease")
        row = rows[0]
        return WorkerLease(self._row_to_job(row), lease_token)

    def finish(
        self,
        workspace_id: UUID,
        job_id: UUID,
        lease_token: UUID,
        target: ResearchJobStatus,
        error_code: str | None = None,
    ) -> ResearchJob:
        result = self._client.rpc(
            "finish_research_run",
            {
                "p_research_run_id": str(job_id),
                "p_workspace_id": str(workspace_id),
                "p_lease_token": str(lease_token),
                "p_target_status": target.value,
                "p_error_code": error_code,
            },
        ).execute()
        if result.data is not True:
            raise RuntimeError("stale or invalid worker lease")
        job = self.get(workspace_id, job_id)
        if job is None:
            raise RuntimeError("finished research job disappeared")
        return job

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
            .select(
                "id,workspace_id,dataset_version_id,workflow_id,status,created_by"
            )
            .execute()
        )
        rows = result.data or []
        if not rows:
            raise ValueError(
                f"invalid or missing research job transition: "
                f"{expected.value} -> {target.value}"
            )
        if len(rows) != 1:
            raise RuntimeError(
                "Supabase research job transition was not unique"
            )
        return self._row_to_job(rows[0])


__all__ = ["SupabaseResearchJobStore"]
