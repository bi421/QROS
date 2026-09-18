"""Worker boundary for asynchronous SaaS research execution."""
from __future__ import annotations

from threading import Event, Thread
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

    def _heartbeat(self, workspace_id, job_id, token, stop):
        interval = max(1.0, self._lease_seconds / 3)
        while not stop.wait(interval):
            try:
                self._store.renew(
                    workspace_id, job_id, token, self._lease_seconds
                )
            except Exception:
                return

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
        stop = Event()
        heartbeat = Thread(
            target=self._heartbeat,
            args=(workspace_id, job.id, lease.token, stop),
            daemon=True,
        )
        heartbeat.start()
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

        finally:
            stop.set()
            heartbeat.join(timeout=1.0)

        target = (
            ResearchJobStatus.SUCCEEDED
            if result.status == "SUCCEEDED"
            else ResearchJobStatus.FAILED
        )
        try:
            self._store.record_result(workspace_id, job_id, lease.token, result)
        except Exception:
            try:
                self._store.finish(
                    workspace_id,
                    job_id,
                    lease.token,
                    ResearchJobStatus.FAILED,
                    error_code="provenance_error",
                )
            except Exception:
                pass
            raise
        self._store.finish(workspace_id, job_id, lease.token, target)
        return result__all__ = ["ResearchExecutor", "ResearchWorker"]
