"""
Technical Analysis Engine — deterministic vectorized indicator framework.

Research-only computation. No trading logic, no signals, no execution.
"""

from researchos.quant_engine.technical.contracts import (
    Bars,
    IndicatorBatch,
    IndicatorCategory,
    IndicatorFamily,
    IndicatorOutput,
    IndicatorSpec,
)
from researchos.quant_engine.technical.engine import (
    INDICATOR_REGISTRY,
    TechnicalAnalysisEngine,
    get_technical_engine,
    register_indicator,
)
from researchos.quant_engine.technical.market_structure import (
    MarketStructureConfig,
    MarketStructureResult,
    StructureBreak,
    SwingPoint,
    detect_market_structure,
    market_structure_variants,
    run_market_structure_variants,
)

from researchos.quant_engine.technical.market_structure_definition import (
    StructureDefinition,
    definitions_from_grid_payload,
)
from researchos.quant_engine.technical.validation import (
    validate_bars,
    validate_params,
    validate_period,
)

__all__ = [
    "StructureDefinition",
    "definitions_from_grid_payload",
    "MarketStructureConfig",
    "MarketStructureResult",
    "StructureBreak",
    "SwingPoint",
    "detect_market_structure",
    "market_structure_variants",
    "run_market_structure_variants",
    "Bars",
    "IndicatorBatch",
    "IndicatorCategory",
    "IndicatorFamily",
    "IndicatorOutput",
    "IndicatorSpec",
    "INDICATOR_REGISTRY",
    "TechnicalAnalysisEngine",
    "get_technical_engine",
    "register_indicator",
    "validate_bars",
    "validate_params",
    "validate_period",
]
