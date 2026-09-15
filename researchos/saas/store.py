"""Persistence boundary for SaaS resources.

The in-memory implementation is intentionally development/test-only. Production
must provide a tenant-isolated persistent implementation (Postgres/Supabase is
the intended deployment target).
"""

from __future__ import annotations

from dataclasses import replace
from threading import Lock
from uuid import UUID

from researchos.saas.contracts import ResearchJob, ResearchJobStatus


class ResearchJobStore:
    """Minimal persistence protocol used by the HTTP layer and worker."""

    def create(self, job: ResearchJob) -> ResearchJob:
        raise NotImplementedError

    def get(self, workspace_id: UUID, job_id: UUID) -> ResearchJob | None:
        raise NotImplementedError

    def count_active(self, workspace_id: UUID) -> int:
        raise NotImplementedError

    def count_monthly(self, workspace_id: UUID) -> int:
        raise NotImplementedError

    def transition(
        self,
        workspace_id: UUID,
        job_id: UUID,
        expected: ResearchJobStatus,
        target: ResearchJobStatus,
    ) -> ResearchJob:
        raise NotImplementedError


class InMemoryResearchJobStore(ResearchJobStore):
    """Deterministic store for tests and local API smoke tests only."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, ResearchJob] = {}
        self._lock = Lock()

    def create(self, job: ResearchJob) -> ResearchJob:
        with self._lock:
            if job.id in self._jobs:
                raise ValueError("research job already exists")
            self._jobs[job.id] = job
            return job

    def get(self, workspace_id: UUID, job_id: UUID) -> ResearchJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.workspace_id != workspace_id:
                return None
            return job

    def count_active(self, workspace_id: UUID) -> int:
        with self._lock:
            return sum(
                job.workspace_id == workspace_id
                and job.status in {ResearchJobStatus.QUEUED, ResearchJobStatus.RUNNING}
                for job in self._jobs.values()
            )

    def count_monthly(self, workspace_id: UUID) -> int:
        """Return the process-local count; production must apply a month predicate."""
        with self._lock:
            return sum(job.workspace_id == workspace_id for job in self._jobs.values())

    def transition(
        self,
        workspace_id: UUID,
        job_id: UUID,
        expected: ResearchJobStatus,
        target: ResearchJobStatus,
    ) -> ResearchJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.workspace_id != workspace_id:
                raise KeyError("research job not found")
            if job.status != expected:
                raise ValueError(
                    f"invalid job transition: {job.status.value} -> {target.value}; "
                    f"expected {expected.value}"
                )
            updated = replace(job, status=target)
            self._jobs[job_id] = updated
            return updated


__all__ = ["InMemoryResearchJobStore", "ResearchJobStore"]
