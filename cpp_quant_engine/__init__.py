"""Source-tree bootstrap and public API for the C++ Quant Engine package.

The canonical Python facade and generated native module live under
`cpp_quant_engine/python/cpp_quant_engine`. This source-tree package
extends its package path so the canonical implementation remains importable
without ad-hoc `sys.path` mutations.

The public symbols below are re-exported from the canonical backend facade
and model/exception modules so `from cpp_quant_engine import ...` remains
stable from the repository root.
"""

from __future__ import annotations

from pathlib import Path

_python_package = Path(__file__).resolve().parent / "python" / "cpp_quant_engine"
if _python_package.is_dir():
    _path = str(_python_package)
    if _path not in __path__:
        __path__.append(_path)

from .backend import (  # noqa: E402
    BacktestEngine,
    CppQuantEngineBackend,
    Risk,
    Simulation,
    Statistics,
    bridge_version,
    default_backend,
    engine_version,
    native_module,
    protocol_version,
    supported_calculation_versions,
)

from .models import (  # noqa: E402
    BacktestRequest,
    BacktestResult,
    Candle,
    MarketData,
    MarketDataRequest,
    MarketDataResult,
    PerformanceReport,
    PerformanceRequest,
    PerformanceResult,
    RiskRequest,
    RiskResult,
    SimulationRequest,
    SimulationResult,
    StatisticsRequest,
    StatisticsResult,
)

from .exceptions import (  # noqa: E402
    BridgeError,
    EmptyDataError,
    HashMismatchError,
    InsufficientDataError,
    InternalError,
    InvalidArgumentError,
    InvalidParameterError,
    InvalidTypeError,
    MalformedDataError,
    OutOfBoundsError,
    UnsupportedVersionError,
    ValidationFailedError,
)

__all__ = [
    "CppQuantEngineBackend",
    "default_backend",
    "BacktestEngine",
    "Statistics",
    "Risk",
    "Simulation",
    "MarketData",
    "Candle",
    "MarketDataRequest",
    "MarketDataResult",
    "StatisticsRequest",
    "StatisticsResult",
    "RiskRequest",
    "RiskResult",
    "SimulationRequest",
    "SimulationResult",
    "BacktestRequest",
    "BacktestResult",
    "PerformanceRequest",
    "PerformanceResult",
    "PerformanceReport",
    "BridgeError",
    "InvalidArgumentError",
    "InvalidParameterError",
    "InvalidTypeError",
    "InsufficientDataError",
    "EmptyDataError",
    "MalformedDataError",
    "OutOfBoundsError",
    "UnsupportedVersionError",
    "ValidationFailedError",
    "HashMismatchError",
    "InternalError",
    "engine_version",
    "bridge_version",
    "protocol_version",
    "supported_calculation_versions",
    "native_module",
]
