"""Load the compiled nanobind module for the canonical QROS C++ engine."""

from __future__ import annotations

from types import ModuleType


def native_module() -> ModuleType:
    """Return the compiled cpp_quant_backend extension."""
    try:
        from . import cpp_quant_backend
    except ImportError as exc:
        raise ImportError(
            "QROS C++ backend is not built or is not importable. "
            "Install QROS with pip install -e . so scikit-build-core "
            "can build and install the native extension."
        ) from exc

    return cpp_quant_backend


__all__ = ["native_module"]
