"""Worker boundary for asynchronous SaaS research execution."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4

from researchos.research_core.contracts import ResearchResult
from researchos.saas.contracts import ResearchJobStatus
from researchos.saas.store import ResearchJobStore


class ResearchExecutor(Protocol):
    def execute(self, job_id: UUID) -> ResearchResult: ...


class ResearchWorker:
    """Fenced coordinator: only the worker holding the lease token may finalize a run."""

    def __init__(
        self,
        store: ResearchJobStore,
        executor: ResearchExecutor,
        *,
        lease_seconds: int = 900,
    ) -> None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        self._store = store
        self._executor = executor
        self._lease_seconds = lease_seconds

    def run_once(
        self,
        workspace_id: UUID,
        job_id: UUID,
    ) -> ResearchResult:
        lease = self._store.claim(
            workspace_id,
            job_id,
            owner=str(uuid4()),
            lease_seconds=self._lease_seconds,
        )
        try:
            result = self._executor.execute(job_id)
        except Exception:
            self._store.finish(
                workspace_id,
                job_id,
                lease.token,
                ResearchJobStatus.FAILED,
                error_code="executor_error",
            )
            raise

        target = (
            ResearchJobStatus.SUCCEEDED
            if result.status == "SUCCEEDED"
            else ResearchJobStatus.FAILED
        )
        self._store.finish(workspace_id, job_id, lease.token, target)
        return result


__all__ = ["ResearchExecutor", "ResearchWorker"]
