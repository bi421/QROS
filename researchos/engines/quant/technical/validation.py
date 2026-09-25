"""Compatibility shim for the canonical technical validation API.

The implementation is authoritative in researchos.quant_engine.technical.validation.
"""

from researchos.quant_engine.technical.validation import (
    validate_bars,
    validate_params,
    validate_period,
    validate_positive_float,
)

__all__ = [
    "validate_bars",
    "validate_period",
    "validate_positive_float",
    "validate_params",
]
