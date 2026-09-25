"""Compatibility shim for the canonical numerical validation API.

The implementation is authoritative in researchos.quant_engine.numerical_validation.
"""

from researchos.quant_engine.numerical_validation import (
    NumericalComparator,
    NumericalComparisonError,
    NumericalValidationResult,
    ValidationStatus,
)

__all__ = [
    "NumericalComparator",
    "NumericalComparisonError",
    "NumericalValidationResult",
    "ValidationStatus",
]
