"""Worker boundary for asynchronous SaaS research execution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from researchos.research_core.contracts import ResearchRequest, ResearchResult
from researchos.saas.contracts import ResearchJobStatus
from researchos.saas.store import ResearchJobStore


class ResearchExecutor(Protocol):
    """Scientific execution adapter supplied by the application composition root."""

    def execute(self, job_id: UUID) -> ResearchResult:
        """Load a persisted job/dataset and invoke the scientific core."""


class ResearchWorker:
    """Small state-machine coordinator; it never owns scientific semantics."""

    def __init__(self, store: ResearchJobStore, executor: ResearchExecutor) -> None:
        self._store = store
        self._executor = executor

    def run_once(self, workspace_id: UUID, job_id: UUID) -> ResearchResult:
        job = self._store.get(workspace_id, job_id)
        if job is None:
            raise KeyError("research job not found")

        self._store.transition(
            workspace_id,
            job_id,
            ResearchJobStatus.QUEUED,
            ResearchJobStatus.RUNNING,
        )
        try:
            result = self._executor.execute(job_id)
        except Exception:
            self._store.transition(
                workspace_id,
                job_id,
                ResearchJobStatus.RUNNING,
                ResearchJobStatus.FAILED,
            )
            raise

        target = (
            ResearchJobStatus.SUCCEEDED
            if result.status == "SUCCEEDED"
            else ResearchJobStatus.FAILED
        )
        self._store.transition(workspace_id, job_id, ResearchJobStatus.RUNNING, target)
        return result


__all__ = ["ResearchExecutor", "ResearchWorker"]
