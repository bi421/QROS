"""Delivery-layer adapters that bind application data to research pipelines."""

from researchos.research_adapters.xauusd_m1 import (
    FrozenXauusdM1Pipeline,
    RawDatasetResolver,
)

__all__ = ["FrozenXauusdM1Pipeline", "RawDatasetResolver"]
