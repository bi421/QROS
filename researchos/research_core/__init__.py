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
from researchos.research_core.intelligence import (\n    Backend,\n    CapabilityRegistry,\n    ComputePlan,\n    DEFAULT_CAPABILITIES,\n    Decision,\n    MethodDecision,\n    ResearchContext,\n    ResearchMethod,\n    ResearchPlanner,\n    ValidationPlan,\n)\nfrom researchos.research_core.runner import (
    FrozenResearchPipeline,
    FrozenXauusdM1Runner,
    PipelineArtifact,
)

__all__ = [
    "Backend",\n    "CapabilityRegistry",\n    "ComputePlan",\n    "DEFAULT_CAPABILITIES",\n    "Decision",\n    "DatasetProvenance",\n    "MethodDecision",\n    "ResearchContext",\n    "ResearchMethod",\n    "ResearchPlanner",\n    "ValidationPlan",
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
