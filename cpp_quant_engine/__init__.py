"""Source-tree bootstrap and public API for the C++ Quant Engine package.

The canonical Python facade and generated native module live under
``cpp_quant_engine/python/cpp_quant_engine``.  This source-tree package
extends its package path so the canonical implementation remains importable
without ad-hoc ``sys.path`` mutations.

The public symbols below are re-exported from the canonical backend facade so
``from cpp_quant_engine import ...`` is stable from the repository root.
"""

from __future__ import annotations

from pathlib import Path

# Make the canonical Python facade (and generated .pyd/.so) a submodule
# location of this source-tree package.
_python_package = Path(__file__).resolve().parent / "python" / "cpp_quant_engine"
if _python_package.is_dir():
    _path = str(_python_package)
    if _path not in __path__:
        __path__.append(_path)

# Public backend API.
from .backend import (  # noqa: E402
    BacktestEngine,
    Risk,
    Simulation,
    Statistics,
    default_backend,
    native_module,
)

__all__ = [
    "BacktestEngine",
    "Risk",
    "Simulation",
    "Statistics",
    "default_backend",
    "native_module",
]
