"""Narrow application-independent boundary for scientific research execution.

This package contains contracts only. It must remain independent of HTTP,
authentication, persistence, billing, and deployment concerns.
"""

from researchos.research_core.contracts import (
    FROZEN_XAUUSD_M1_WORKFLOW,
    ResearchArtifact,
    ResearchDataset,
    ResearchRequest,
    ResearchResult,
    ResearchRunner,
)

__all__ = [
    "FROZEN_XAUUSD_M1_WORKFLOW",
    "ResearchArtifact",
    "ResearchDataset",
    "ResearchRequest",
    "ResearchResult",
    "ResearchRunner",
]
