"""Worker boundary for asynchronous SaaS research execution."""
from __future__ import annotations

from threading import Event, Thread
import time
from typing import Protocol
from uuid import UUID, uuid4

from researchos.research_core.contracts import ResearchResult
from researchos.saas.contracts import ResearchJobStatus
from researchos.saas.observability import StructuredRequestObserver, configure_tracing, emit_log, span
from researchos.saas.store import ResearchJobStore


class ResearchExecutor(Protocol):
    def execute(self, job_id: UUID) -> ResearchResult: ...


class ResearchWorker:
    """Fenced coordinator with request/tenant/job correlation across execution."""

    def __init__(
        self,
        store: ResearchJobStore,
        executor: ResearchExecutor,
        *,
        lease_seconds: int = 900,
        observability: StructuredRequestObserver | None = None,
    ) -> None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        configure_tracing()
        self._store = store
        self._executor = executor
        self._lease_seconds = lease_seconds
        self._observability = observability or StructuredRequestObserver()

    def _heartbeat(self, workspace_id: UUID, job_id: UUID, token: UUID, stop: Event) -> None:
        interval = max(1.0, self._lease_seconds / 3)
        while not stop.wait(interval):
            try:
                self._store.renew(workspace_id, job_id, token, self._lease_seconds)
            except Exception:
                return

    def run_once(
        self,
        workspace_id: UUID,
        job_id: UUID,
        *,
        request_id: str | None = None,
    ) -> ResearchResult:
        with span("qros.job", request_id=request_id, tenant_id=workspace_id, job_id=job_id):
            lease = self._store.claim(
                workspace_id,
                job_id,
                owner=str(uuid4()),
                lease_seconds=self._lease_seconds,
            )
            emit_log(
                level=20,
                message="research job claimed by worker",
                request_id=request_id,
                tenant_id=workspace_id,
                job_id=job_id,
            )
            stop = Event()
            heartbeat = Thread(
                target=self._heartbeat,
                args=(workspace_id, job_id, lease.token, stop),
                daemon=True,
            )
            heartbeat.start()
            started_at = time.perf_counter()
            try:
                with span(
                    "qros.execution",
                    request_id=request_id,
                    tenant_id=workspace_id,
                    job_id=job_id,
                ):
                    result = self._executor.execute(job_id)
            except Exception:
                self._store.finish(
                    workspace_id,
                    job_id,
                    lease.token,
                    ResearchJobStatus.FAILED,
                    error_code="executor_error",
                )
                self._observability.metrics.inc_job_failed()
                emit_log(
                    level=40,
                    message="research job execution failed",
                    request_id=request_id,
                    tenant_id=workspace_id,
                    job_id=job_id,
                    duration_ms=(__import__("time").perf_counter() - started_at) * 1000.0,
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
                self._observability.metrics.inc_job_failed()
                emit_log(
                    level=40,
                    message="research job provenance persistence failed",
                    request_id=request_id,
                    tenant_id=workspace_id,
                    job_id=job_id,
                )
                raise
            self._store.finish(workspace_id, job_id, lease.token, target)
            if target == ResearchJobStatus.FAILED:
                self._observability.metrics.inc_job_failed()
            emit_log(
                level=20 if target == ResearchJobStatus.SUCCEEDED else 40,
                message=f"research job {target.value}",
                request_id=request_id,
                tenant_id=workspace_id,
                job_id=job_id,
                duration_ms=(__import__("time").perf_counter() - started_at) * 1000.0,
            )
            return result


__all__ = ["ResearchExecutor", "ResearchWorker"]
