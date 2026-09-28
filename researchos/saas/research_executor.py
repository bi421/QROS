"""Production executor bridge for governed SaaS research jobs."""

from __future__ import annotations

import hashlib
from uuid import UUID

from researchos.research_adapters.xauusd_m1 import FrozenXauusdM1Pipeline
from researchos.research_core.contracts import ResearchDataset, ResearchRequest, ResearchResult
from researchos.research_core.runner import FrozenXauusdM1Runner
from researchos.saas.datasets import DatasetStorage, DatasetStore, DatasetVersion
from researchos.saas.store import ResearchJobStore


class _BoundRawDatasetResolver:
    def __init__(self, version: DatasetVersion, raw: bytes) -> None:
        self._version = version
        self._raw = raw

    def __call__(self, request: ResearchRequest) -> bytes:
        if request.dataset.dataset_id != str(self._version.dataset_id):
            raise ValueError("research request dataset id does not match resolved version")
        if request.dataset.content_sha256 != self._version.content_sha256:
            raise ValueError("research request dataset SHA does not match resolved version")
        return self._raw


class GovernedResearchExecutor:
    """Resolve one immutable tenant-scoped dataset and invoke the frozen runner."""

    def __init__(
        self,
        store: ResearchJobStore,
        dataset_store: DatasetStore,
        dataset_storage: DatasetStorage,
        workspace_id: UUID,
    ) -> None:
        self._store = store
        self._dataset_store = dataset_store
        self._dataset_storage = dataset_storage
        self._workspace_id = workspace_id

    def execute(self, job_id: UUID) -> ResearchResult:
        job = self._store.get(self._workspace_id, job_id)
        if job is None:
            raise KeyError("research job not found for workspace")

        version = self._dataset_store.get_version(
            self._workspace_id,
            job.dataset_version_id,
        )
        if version is None:
            raise KeyError("dataset version not found for workspace")
        if version.content_sha256 != job.source_dataset_sha256:
            raise ValueError("resolved dataset SHA does not match persisted job source SHA")

        raw = self._dataset_storage.download(version.storage_path)
        if len(raw) != version.byte_size:
            raise ValueError("materialized dataset byte size does not match dataset version")
        actual_sha256 = hashlib.sha256(raw).hexdigest()
        if actual_sha256 != version.content_sha256:
            raise ValueError("materialized dataset SHA does not match dataset version")

        dataset = ResearchDataset.from_content(
            dataset_id=str(version.dataset_id),
            asset="XAUUSD",
            timeframe="M1",
            content=raw,
            rows=(),
        )
        if dataset.content_sha256 != job.source_dataset_sha256:
            raise ValueError("ResearchDataset SHA does not match persisted job source SHA")
        request = ResearchRequest(dataset=dataset, workflow_id=job.workflow_id)
        runner = FrozenXauusdM1Runner(
            FrozenXauusdM1Pipeline(_BoundRawDatasetResolver(version, raw))
        )
        result = runner.run(request)
        if result.source_dataset_sha256 != job.source_dataset_sha256:
            raise ValueError("ResearchResult source SHA does not match persisted job source SHA")
        return result


__all__ = ["GovernedResearchExecutor"]
