"""Pipeline coordination for ResearchOS — connecting object lifecycle stages."""

from researchos.pipeline.pipeline import ReferenceValidator, ResearchPipeline

__all__ = [
    "ResearchPipeline",
    "ReferenceValidator",
]
