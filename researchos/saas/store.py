"""Persistence boundary for SaaS resources."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import UUID, uuid4

from researchos.saas.contracts import ResearchJob, ResearchJobStatus


@dataclass(frozen=True)
class WorkerLease:
    job: ResearchJob
    token: UUID


class ResearchJobStore:
    def create(self, job: ResearchJob) -> ResearchJob:
        raise NotImplementedError

    def get(self, workspace_id: UUID, job_id: UUID) -> ResearchJob | None:
        raise NotImplementedError

    def count_active(self, workspace_id: UUID) -> int:
        raise NotImplementedError

    def count_monthly(self, workspace_id: UUID) -> int:
        raise NotImplementedError

    def claim(
        self,
        workspace_id: UUID,
        job_id: UUID,
        owner: str,
        lease_seconds: int,
    ) -> WorkerLease:
        raise NotImplementedError

    def renew(
        self,
        workspace_id: UUID,
        job_id: UUID,
        lease_token: UUID,
        lease_seconds: int,
    ) -> WorkerLease:
        raise NotImplementedError

    def renew(
        self,
        workspace_id: UUID,
        job_id: UUID,
        lease_token: UUID,
        lease_seconds: int,
    ) -> WorkerLease:
        if lease_seconds < 1:
            raise ValueError("invalid worker lease")
        with self._lock:
            job = self._jobs.get(job_id)
            lease = self._leases.get(job_id)
            if (
                job is None
                or job.workspace_id != workspace_id
                or job.status != ResearchJobStatus.RUNNING
                or lease is None
                or lease[0] != lease_token
                or lease[1] <= self._clock()
            ):
                raise RuntimeError("stale or invalid worker lease")
            expires = self._clock() + timedelta(seconds=lease_seconds)
            self._leases[job_id] = (lease_token, expires)
            return WorkerLease(job, lease_token)

    def finish(
        self,
        workspace_id: UUID,
        job_id: UUID,
        lease_token: UUID,
        target: ResearchJobStatus,
        error_code: str | None = None,
    ) -> ResearchJob:
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
    def __init__(self, *, clock=None) -> None:
        self._jobs: dict[UUID, ResearchJob] = {}
        self._leases: dict[UUID, tuple[UUID, datetime]] = {}
        self._lock = Lock()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

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
                and job.status
                in {ResearchJobStatus.QUEUED, ResearchJobStatus.RUNNING}
                for job in self._jobs.values()
            )

    def count_monthly(self, workspace_id: UUID) -> int:
        with self._lock:
            return sum(
                job.workspace_id == workspace_id
                for job in self._jobs.values()
            )

    def claim(
        self,
        workspace_id: UUID,
        job_id: UUID,
        owner: str,
        lease_seconds: int,
    ) -> WorkerLease:
        if not owner.strip() or lease_seconds < 1:
            raise ValueError("invalid worker lease")
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.workspace_id != workspace_id:
                raise KeyError("research job not found")
            existing_lease = self._leases.get(job_id)
            if job.status == ResearchJobStatus.RUNNING:
                if existing_lease is None or existing_lease[1] > self._clock():
                    raise RuntimeError("research job is already claimed")
            elif job.status != ResearchJobStatus.QUEUED:
                raise RuntimeError("research job is already claimed")
            token = uuid4()
            updated = replace(job, status=ResearchJobStatus.RUNNING)
            self._jobs[job_id] = updated
            self._leases[job_id] = (token, self._clock() + timedelta(seconds=lease_seconds))
            return WorkerLease(updated, token)

    def finish(
        self,
        workspace_id: UUID,
        job_id: UUID,
        lease_token: UUID,
        target: ResearchJobStatus,
        error_code: str | None = None,
    ) -> ResearchJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.workspace_id != workspace_id:
                raise KeyError("research job not found")
            if (
                job.status != ResearchJobStatus.RUNNING
                or self._leases.get(job_id, (None, None))[0] != lease_token
            ):
                raise RuntimeError("stale or invalid worker lease")
            if target not in {
                ResearchJobStatus.SUCCEEDED,
                ResearchJobStatus.FAILED,
            }:
                raise ValueError("invalid terminal target")
            updated = replace(job, status=target)
            self._jobs[job_id] = updated
            self._leases.pop(job_id, None)
            return updated

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
                    f"invalid job transition: {job.status.value} -> "
                    f"{target.value}; expected {expected.value}"
                )
            updated = replace(job, status=target)
            self._jobs[job_id] = updated
            return updated


__all__ = ["InMemoryResearchJobStore", "ResearchJobStore", "WorkerLease"]
