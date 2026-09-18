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
from researchos.research_core.execution import (
    ExecutionBinding,
    ExecutionRegistry,
    validate_backend_capability,
)
from researchos.research_core.intelligence import (
    Backend,
    CapabilityRegistry,
    ComputePlan,
    DEFAULT_CAPABILITIES,
    Decision,
    MethodDecision,
    ResearchContext,
    ResearchMethod,
    ResearchPlanner,
    ValidationPlan,
)
from researchos.research_core.runner import (
    FrozenResearchPipeline,
    FrozenXauusdM1Runner,
    PipelineArtifact,
)

__all__ = [
    "Backend",
    "CapabilityRegistry",
    "ComputePlan",
    "DEFAULT_CAPABILITIES",
    "DatasetProvenance",
    "Decision",
    "ExecutionBinding",
    "ExecutionRegistry",
    "FROZEN_XAUUSD_M1_WORKFLOW",
    "FrozenResearchPipeline",
    "FrozenXauusdM1Runner",
    "MethodDecision",
    "PipelineArtifact",
    "ResearchArtifact",
    "ResearchContext",
    "ResearchDataset",
    "ResearchMethod",
    "ResearchPlanner",
    "ResearchRequest",
    "ResearchResult",
    "ResearchRunner",
    "ValidationPlan",
    "validate_backend_capability",
]
