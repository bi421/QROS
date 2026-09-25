"""Compatibility shim for the canonical backend capabilities API.

The implementation is authoritative in researchos.quant_engine.capabilities.
"""

from researchos.quant_engine.capabilities import (
    QUANT_OPERATIONS,
    REFERENCE_BACKEND_NAME,
    REFERENCE_BACKEND_VERSION,
    BackendCapabilities,
    BackendCapabilitiesError,
    default_capabilities,
)

__all__ = [
    "QUANT_OPERATIONS",
    "REFERENCE_BACKEND_NAME",
    "REFERENCE_BACKEND_VERSION",
    "BackendCapabilities",
    "BackendCapabilitiesError",
    "default_capabilities",
]
