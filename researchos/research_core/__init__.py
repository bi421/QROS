"""Application-independent scientific research core contracts and runner."""

from researchos.research_core.contracts import (
    FROZEN_XAUUSD_M1_WORKFLOW,
    DatasetProvenance,
    ResearchArtifact,
    ResearchDataset,
    ResearchRequest,
    ResearchResult,
    ResearchRunner,
)
from researchos.research_core.runner import (
    FrozenResearchPipeline,
    FrozenXauusdM1Runner,
    PipelineArtifact,
)

__all__ = [
    "DatasetProvenance",
    "FROZEN_XAUUSD_M1_WORKFLOW",
    "FrozenResearchPipeline",
    "FrozenXauusdM1Runner",
    "PipelineArtifact",
    "ResearchArtifact",
    "ResearchDataset",
    "ResearchRequest",
    "ResearchResult",
    "ResearchRunner",
]
