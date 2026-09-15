"""Application-neutral runner adapter for the frozen scientific workflow.

The runner owns only the core execution envelope. Delivery layers provide the
actual scientific pipeline callable; HTTP, persistence, authentication, and
billing remain outside this package.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from researchos.research_core.contracts import (
    FROZEN_XAUUSD_M1_WORKFLOW,
    ResearchArtifact,
    ResearchRequest,
    ResearchResult,
)


@dataclass(frozen=True)
class PipelineArtifact:
    """Immutable bytes emitted by a scientific pipeline execution."""

    artifact_id: str
    kind: str
    content: bytes


class FrozenResearchPipeline(Protocol):
    """Callable scientific pipeline supplied by the existing research layer."""

    def __call__(self, request: ResearchRequest) -> Iterable[PipelineArtifact]:
        """Execute the frozen workflow and yield its output artifacts."""


class FrozenXauusdM1Runner:
    """Adapt the frozen XAUUSD M1 pipeline to the ResearchRunner contract."""

    workflow_id = FROZEN_XAUUSD_M1_WORKFLOW

    def __init__(self, pipeline: FrozenResearchPipeline) -> None:
        self._pipeline = pipeline

    def run(self, request: ResearchRequest) -> ResearchResult:
        if request.workflow_id != self.workflow_id:
            raise ValueError(f"unsupported workflow_id: {request.workflow_id!r}")

        try:
            artifacts = tuple(self._pipeline(request))
            result_artifacts = tuple(
                ResearchArtifact(
                    artifact_id=artifact.artifact_id,
                    kind=artifact.kind,
                    content_sha256=hashlib.sha256(artifact.content).hexdigest(),
                )
                for artifact in artifacts
            )
            return ResearchResult(
                status="SUCCEEDED",
                source_dataset_sha256=request.dataset.content_sha256,
                artifacts=result_artifacts,
            )
        except Exception as exc:
            return ResearchResult(
                status="FAILED",
                source_dataset_sha256=request.dataset.content_sha256,
                failures=(f"{type(exc).__name__}: {exc}",),
            )


__all__ = [
    "FrozenResearchPipeline",
    "FrozenXauusdM1Runner",
    "PipelineArtifact",
]
