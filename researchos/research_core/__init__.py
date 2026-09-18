"""Application-independent scientific research core contracts and runner."""

from researchos.research_core.analysis_result import AnalysisResult, AnalysisState
from researchos.research_core.contracts import (
    FROZEN_XAUUSD_M1_WORKFLOW,
    DatasetProvenance,
    ResearchArtifact,
    ResearchDataset,
    ResearchRequest,
    ResearchResult,
    ResearchRunner,
)
from researchos.research_core.evidence import EvidenceArtifact, EvidenceKind
from researchos.research_core.execution import (
    ExecutionBinding,
    ExecutionRegistry,
    registry_for_backend,
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
    "AnalysisResult",
    "AnalysisState",
    "Backend",
    "CapabilityRegistry",
    "ComputePlan",
    "DEFAULT_CAPABILITIES",
    "Decision",
    "DatasetProvenance",
    "ExecutionBinding",
    "ExecutionRegistry",\n    "EvidenceArtifact",\n    "EvidenceKind",
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
    "registry_for_backend",
    "validate_backend_capability",
]
