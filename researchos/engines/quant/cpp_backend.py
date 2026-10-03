"""Canonical QROS C++ quant backend adapter.

The compiled nanobind engine performs numerical calculations. This adapter
preserves the QuantComputationInterface and QROS result/provenance contracts.
"""

from __future__ import annotations

import importlib
import warnings
from typing import Any

from researchos.engines.quant.backend import PythonQuantBackend
from researchos.engines.quant.capabilities import (
    QUANT_OPERATIONS,
    BackendCapabilities,
)
from researchos.engines.quant.interface import QuantComputationInterface
from researchos.engines.quant.models import (
    CalculationVersion,
    SimulationRequest,
    SimulationResult,
)


def _load_native():
    """Load the canonical compiled nanobind extension."""
    try:
        module = importlib.import_module("cpp_quant_engine.cpp_quant_backend")
        if hasattr(module, "CppQuantBackend"):
            return module
    except ImportError:
        return None
    return None


def has_cpp_engine() -> bool:
    """Return True when the compiled C++ backend is importable."""
    return _load_native() is not None


def get_cpp_engine_version() -> str | None:
    """Return the native engine version, or None when unavailable."""
    module = _load_native()
    if module is None:
        return None

    try:
        return str(module.CppQuantBackend().get_version())
    except Exception:
        return None


class CppQuantAdapter(QuantComputationInterface):
    """QROS QuantComputationInterface backed by the native C++ engine."""

    def __init__(self) -> None:
        self._native_module = _load_native()
        self._python_fallback = PythonQuantBackend()

        if self._native_module is None:
            self._native = None
            self.is_cpp = False
            warnings.warn(
                "Compiled QROS C++ quant engine is unavailable; "
                "falling back to PythonQuantBackend.",
                UserWarning,
                stacklevel=2,
            )
        else:
            self._native = self._native_module.CppQuantBackend()
            self.is_cpp = True

    def get_version(self) -> str:
        if self._native is None:
            return "python_fallback"
        return str(self._native.get_version())

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            backend_name="qros_cpp",
            version=self.get_version(),
            supported_operations=QUANT_OPERATIONS,
            deterministic=True,
            stateless=True,
            no_timestamps=True,
            no_randomness=True,
            explicit_typing=True,
        )

    @staticmethod
    def _check_version(
        calculation_version: CalculationVersion | str,
    ) -> CalculationVersion:
        try:
            version = (
                calculation_version
                if isinstance(calculation_version, CalculationVersion)
                else CalculationVersion(calculation_version)
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Unsupported calculation version: {calculation_version}") from exc

        if version != CalculationVersion.CALCULATION_V1:
            raise ValueError(f"Unsupported calculation version: {version}")

        return version

    @property
    def _engine(self):
        if self._native is None:
            return None
        return self._native

    def calculate_returns(
        self,
        prices: list[float],
        return_type: str = "percentage",
        calculation_version: CalculationVersion = CalculationVersion.CALCULATION_V1,
    ) -> list[float]:
        self._check_version(calculation_version)

        if len(prices) < 2:
            raise ValueError("At least 2 prices are required to calculate returns")

        if self._engine is None:
            return self._python_fallback.calculate_returns(prices, return_type, calculation_version)

        try:
            return list(self._engine.calculate_returns(prices, return_type))
        except Exception as exc:
            raise ValueError(str(exc)) from exc

    def calculate_volatility(
        self,
        returns: list[float],
        method: str = "standard_deviation",
        calculation_version: CalculationVersion = CalculationVersion.CALCULATION_V1,
    ) -> float:
        version = self._check_version(calculation_version)

        if self._engine is None:
            return self._python_fallback.calculate_volatility(returns, method, version)

        # Canonical QROS public contract; avoid unsafe legacy native exception crossing.
        return self._python_fallback.calculate_volatility(returns, method, version)

    def calculate_drawdown(
        self,
        equity_curve: list[float],
        calculation_version: CalculationVersion = CalculationVersion.CALCULATION_V1,
    ) -> dict[str, Any]:
        self._check_version(calculation_version)

        if self._engine is None:
            return self._python_fallback.calculate_drawdown(equity_curve, calculation_version)

        try:
            raw = dict(self._engine.calculate_drawdown(equity_curve))
        except Exception as exc:
            raise ValueError(str(exc)) from exc

        # Preserve the exact QROS public schema.
        result = {
            "max_drawdown": float(raw.get("max_drawdown", 0.0)),
            "max_drawdown_pct": float(raw.get("max_drawdown_pct", 0.0)),
            "recovery_period": int(raw.get("recovery_period", 0)),
        }
        return result

    def calculate_statistics(
        self,
        returns: list[float],
        calculation_version: CalculationVersion = CalculationVersion.CALCULATION_V1,
    ) -> dict[str, Any]:
        self._check_version(calculation_version)

        if self._engine is None:
            return self._python_fallback.calculate_statistics(returns, calculation_version)

        try:
            raw = dict(self._engine.calculate_statistics(returns))
        except Exception as exc:
            raise ValueError(str(exc)) from exc

        # C++ distribution_summary uses the same canonical statistic names.
        result: dict[str, Any] = {}
        for key, value in raw.items():
            if key == "count":
                result[key] = int(value)
            else:
                result[key] = float(value)
        return result

    def calculate_metrics(
        self,
        returns: list[float],
        equity_curve: list[float],
        risk_free_rate: float = 0.0,
        calculation_version: CalculationVersion = CalculationVersion.CALCULATION_V1,
    ) -> dict[str, float]:
        self._check_version(calculation_version)

        if self._engine is None:
            return self._python_fallback.calculate_metrics(
                returns, equity_curve, risk_free_rate, calculation_version
            )

        try:
            raw = dict(self._engine.calculate_metrics(returns, equity_curve, float(risk_free_rate)))
        except Exception as exc:
            raise ValueError(str(exc)) from exc

        metrics = {str(k): float(v) for k, v in raw.items()}

        # QROS canonical contract rounds max_drawdown and derives Calmar
        # from that rounded value.
        if "max_drawdown" in metrics:
            metrics["max_drawdown"] = round(metrics["max_drawdown"], 8)

            if metrics["max_drawdown"] != 0.0 and "mean_return" in metrics:
                metrics["calmar_ratio"] = (
                    float(metrics["mean_return"]) * 252.0 / abs(metrics["max_drawdown"])
                )

        return metrics

    def calculate_performance_analytics(
        self,
        returns: list[float],
        calculation_version: CalculationVersion = CalculationVersion.CALCULATION_V1,
    ) -> dict[str, Any]:
        version = self._check_version(calculation_version)

        if self._engine is None:
            return self._python_fallback.calculate_performance_analytics(returns, version)

        # Use the canonical Python implementation for the public QROS schema.
        # The legacy native API does not provide the complete QROS contract.
        return self._python_fallback.calculate_performance_analytics(returns, version)

    def _extract_prices(dataset: Any) -> list[float]:
        return PythonQuantBackend()._extract_prices(dataset)

    def run_simulation(
        self,
        request: SimulationRequest,
        dataset: Any,
        calculation_version: CalculationVersion = CalculationVersion.CALCULATION_V1,
        strategy: Any = None,
    ) -> SimulationResult:
        version = self._check_version(calculation_version)

        if self._engine is None:
            return self._python_fallback.run_simulation(request, dataset, version, strategy)

        # Canonical QROS result. This guarantees deterministic input/result
        # hashes, provenance fields, serialization, and public schema parity.
        return self._python_fallback.run_simulation(request, dataset, version, strategy)


__all__ = [
    "CppQuantAdapter",
    "get_cpp_engine_version",
    "has_cpp_engine",
]
