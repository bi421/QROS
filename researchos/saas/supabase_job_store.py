"""Supabase-backed persistence for tenant-scoped research jobs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from researchos.research_core.contracts import ResearchResult
from researchos.saas.contracts import ResearchJob, ResearchJobStatus
from researchos.saas.provenance import ResearchRunResultRecord, build_result_record
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
            source_dataset_sha256=str(row["source_dataset_sha256"]),
            created_by=(UUID(str(row["created_by"])) if row.get("created_by") else None),
            attempt_count=int(row.get("attempt_count", 0)),
            max_attempts=int(row.get("max_attempts", 3)),
            error_code=str(row["error_code"]) if row.get("error_code") else None,
            claim_id=str(row["claim_id"]) if row.get("claim_id") else None,
            plan_hash=str(row["plan_hash"]) if row.get("plan_hash") else None,
            created_at=datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00")),
        )

    def create_idempotent(
        self,
        workspace_id: UUID,
        job: ResearchJob,
        idempotency_key: str,
        request_fingerprint: str,
        response_body: dict[str, object],
    ) -> tuple[ResearchJob, bool]:
        if job.workspace_id != workspace_id:
            raise ValueError("research job workspace does not match tenant")
        if job.created_by is None:
            raise ValueError("Supabase research jobs require created_by")
        rpc_name = (
            "create_governed_research_run_idempotent"
            if job.claim_id is not None
            else "create_research_run_idempotent"
        )
        rpc_args = {
            "p_research_run_id": str(job.id),
            "p_workspace_id": str(job.workspace_id),
            "p_dataset_version_id": str(job.dataset_version_id),
            "p_workflow_id": job.workflow_id,
            "p_created_by": str(job.created_by),
            "p_idempotency_key": idempotency_key,
            "p_request_fingerprint": request_fingerprint,
            "p_response_body": response_body,
        }
        if job.claim_id is not None:
            rpc_args["p_claim_id"] = job.claim_id
            rpc_args["p_plan_hash"] = job.plan_hash
        result = self._client.rpc(rpc_name, rpc_args).execute()
        rows = result.data or []
        if len(rows) != 1:
            raise RuntimeError("idempotent research run creation returned no unique row")
        row = rows[0]
        job_row = row.get("job", row)
        return self._row_to_job(job_row), bool(row.get("replayed", False))

    def create(self, workspace_id: UUID, job: ResearchJob) -> ResearchJob:
        if job.workspace_id != workspace_id:
            raise ValueError("research job workspace does not match tenant")
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
                    "source_dataset_sha256": job.source_dataset_sha256,
                    "created_by": str(job.created_by),
                    "claim_id": job.claim_id,
                    "plan_hash": job.plan_hash,
                }
            )
            .select("id,workspace_id,dataset_version_id,workflow_id,status,source_dataset_sha256,created_by,attempt_count,max_attempts,error_code,claim_id,plan_hash,created_at")
            .execute()
        )
        rows = result.data or []
        if len(rows) != 1:
            raise RuntimeError("Supabase research job insert returned no unique row")
        return self._row_to_job(rows[0])

    def record_result(self, workspace_id: UUID, job_id: UUID, lease_token: UUID, result: ResearchResult) -> ResearchRunResultRecord:
        job = self.get(workspace_id, job_id)
        if job is None:
            raise RuntimeError("research job disappeared before result persistence")
        record = build_result_record(
            workspace_id,
            job_id,
            result,
            claim_id=UUID(job.claim_id) if job.claim_id else None,
            plan_hash=job.plan_hash,
        )
        response = self._client.rpc(
            "record_research_run_result",
            {
                "p_workspace_id": str(workspace_id),
                "p_research_run_id": str(job_id),
                "p_lease_token": str(lease_token),
                "p_status": result.status,
                "p_manifest_sha256": record.manifest_sha256,
                "p_artifacts": [
                    {"artifact_id": a.artifact_id, "kind": a.kind, "content_sha256": a.content_sha256}
                    for a in result.artifacts
                ],
                "p_failures": list(result.failures),
            },
        ).execute()
        if response.data is None:
            raise RuntimeError("research result persistence returned no record")
        return record

    def get_result(self, workspace_id: UUID, job_id: UUID) -> ResearchRunResultRecord | None:
        result = (
            self._client.table("research_run_result")
            .select("workspace_id,research_run_id,source_dataset_sha256,status,manifest_sha256,failures")
            .eq("workspace_id", str(workspace_id))
            .eq("research_run_id", str(job_id))
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        row = rows[0]
        run_rows = (
            self._client.table("research_run")
            .select("claim_id,plan_hash")
            .eq("workspace_id", str(workspace_id))
            .eq("id", str(job_id))
            .limit(1)
            .execute()
        )
        if not (run_rows.data or []):
            raise RuntimeError("research run disappeared while reading result")
        run_row = run_rows.data[0]
        artifact_rows = (
            self._client.table("research_run_artifact")
            .select("artifact_id,kind,content_sha256")
            .eq("workspace_id", str(workspace_id))
            .eq("research_run_id", str(job_id))
            .order("artifact_id")
            .execute()
        )
        from researchos.research_core.contracts import ResearchArtifact
        artifacts = tuple(
            ResearchArtifact(str(item["artifact_id"]), str(item["kind"]), str(item["content_sha256"]))
            for item in (artifact_rows.data or [])
        )
        return ResearchRunResultRecord(
            workspace_id=UUID(str(row["workspace_id"])),
            research_run_id=UUID(str(row["research_run_id"])),
            claim_id=UUID(str(run_row["claim_id"])) if run_row.get("claim_id") else None,
            plan_hash=str(run_row["plan_hash"]) if run_row.get("plan_hash") else None,
            source_dataset_sha256=str(row["source_dataset_sha256"]),
            status=str(row["status"]),
            manifest_sha256=str(row["manifest_sha256"]),
            artifacts=artifacts,
            failures=tuple(str(item) for item in (row.get("failures") or [])),
        )

    def get(self, workspace_id: UUID, job_id: UUID) -> ResearchJob | None:
        result = (
            self._client.table("research_run")
            .select("id,workspace_id,dataset_version_id,workflow_id,status,source_dataset_sha256,created_by,attempt_count,max_attempts,error_code,claim_id,plan_hash,created_at")
            .eq("workspace_id", str(workspace_id))
            .eq("id", str(job_id))
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return self._row_to_job(rows[0]) if rows else None

    def list(self, workspace_id: UUID, *, limit: int, offset: int, status: ResearchJobStatus | None = None, workflow_id: str | None = None, sort_by: str = "created_at", sort_order: str = "desc") -> tuple[list[ResearchJob], int]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("invalid pagination")
        if sort_by not in {"created_at", "status", "workflow_id"}:
            raise ValueError("invalid sort field")
        if sort_order not in {"asc", "desc"}:
            raise ValueError("invalid sort order")
        query = (
            self._client.table("research_run")
            .select("id,workspace_id,dataset_version_id,workflow_id,status,source_dataset_sha256,created_by,attempt_count,max_attempts,error_code,claim_id,plan_hash,created_at", count="exact")
            .eq("workspace_id", str(workspace_id))
        )
        if status is not None:
            query = query.eq("status", status.value)
        if workflow_id is not None:
            query = query.eq("workflow_id", workflow_id)
        result = query.order(sort_by, desc=sort_order == "desc").range(offset, offset + limit - 1).execute()
        return [self._row_to_job(row) for row in (result.data or [])], int(result.count or 0)

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
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
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
        return WorkerLease(self._row_to_job(row), UUID(str(row["lease_token"])))

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
            .select("id,workspace_id,dataset_version_id,workflow_id,status,source_dataset_sha256,created_by,attempt_count,max_attempts,error_code,claim_id,plan_hash,created_at")
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
