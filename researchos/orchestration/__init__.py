"""
Research Orchestration Layer (Q14) — pure coordinator.

This module is a PURE COORDINATOR.  It never persists, never writes to
repositories or registries, and never constructs or mutates graphs.  It
wires the locked modules (Dataset Builder, Walk-Forward Validation,
Training Framework) into a single deterministic research pipeline and
returns an immutable ``PipelineReport``.

Public API:

    ResearchOrchestrator    dependency-injected coordinator
    PipelineReport          immutable, hashable, serializable outcome
    PipelineStage           ordered pipeline stages
    PipelineStatus          lifecycle status
    EvidenceNodeDescriptor  pure node descriptor for Intelligence Layer
    EvidenceEdgeDescriptor  pure edge descriptor for Intelligence Layer
"""

from .contracts import (
    ORCHESTRATION_VERSION,
    EvidenceEdgeDescriptor,
    EvidenceNodeDescriptor,
    OrchestrationError,
    PipelineReport,
    PipelineStage,
    PipelineStatus,
)
from .engine import ResearchOrchestrator
from .parallel import (
    ParallelBranchResult,
    ParallelOrchestrationError,
    ParallelResearchExecutor,
    ParallelResearchResult,
    ResearchBranch,
    ResearchWave,
)

__all__ = [
    "ORCHESTRATION_VERSION",
    "OrchestrationError",
    "PipelineStage",
    "PipelineStatus",
    "EvidenceNodeDescriptor",
    "EvidenceEdgeDescriptor",
    "PipelineReport",
    "ResearchOrchestrator",
    "ParallelOrchestrationError",
    "ResearchBranch",
    "ResearchWave",
    "ParallelBranchResult",
    "ParallelResearchResult",
    "ParallelResearchExecutor",
]
