"""Load the compiled nanobind module for the canonical QROS C++ engine."""

from __future__ import annotations

from types import ModuleType


def native_module() -> ModuleType:
    """Return the canonical compiled QROS C++ quant backend."""
    try:
        from cpp_quant_engine import cpp_quant_backend
    except ImportError as exc:
        raise ImportError(
            "QROS C++ backend is not built or is not importable. "
            "Build/install QROS with pip install -e ."
        ) from exc
    return cpp_quant_backend


__all__ = ["native_module"]
