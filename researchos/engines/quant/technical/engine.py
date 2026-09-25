"""Compatibility shim for the canonical technical engine API.

The implementation is authoritative in researchos.quant_engine.technical.engine.
"""

from researchos.quant_engine.technical.engine import (
    INDICATOR_REGISTRY,
    TechnicalAnalysisEngine,
    get_technical_engine,
    register_indicator,
)

__all__ = [
    "INDICATOR_REGISTRY",
    "TechnicalAnalysisEngine",
    "get_technical_engine",
    "register_indicator",
]
