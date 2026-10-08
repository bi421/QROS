"""
CppQuantAdapter — QuantComputationInterface implementation backed by the C++ engine.

The adapter delegates numerical computation to the compiled C++20 quant engine
through the native module loader (``cpp_quant_engine.backend.native_module``),
while presenting results through the ResearchOS data contract
(``SimulationResult`` / ``SimulationRequest``).

Design:
    - ``CppQuantAdapter`` implements ``QuantComputationInterface`` exactly, so
      it can be swapped in via ``HistoricalSimulationEngine.set_backend(...)``
      with zero changes to upper layers.
    - Constructor signature matches ``PythonQuantBackend`` for drop-in use.
    - Falls back to ``PythonQuantBackend`` when the compiled module is not
      importable, so the interface never breaks.
    - ``calculate_performance_analytics`` and the ``performance`` field are
      computed by the ResearchOS reference implementation
      (``compute_performance_analytics``) so the ResearchOS schema is preserved
      regardless of the C++ performance analytics schema.
    - ResearchOS schema normalization is applied to C++ outputs:
        * ``statistics["count"]`` -> int
        * ``metrics["max_drawdown"]`` -> rounded to 8 decimal places
        * ``metrics["calmar_ratio"]`` -> recomputed from the rounded
          ``max_drawdown`` (ResearchOS definition)
        * ``drawdown["max_drawdown"]`` / ``max_drawdown_pct`` / ``recovery_period``
          -> ResearchOS precision / int
    - Validation contract mirrors ``PythonQuantBackend`` (``ValueError`` on
      empty / insufficient data, unsupported calculation version, unknown
      method), and residual C++ validation errors surface as ``ValueError``.

The native module loader is the single integration point for the compiled
C++ backend. The legacy ``cpp_quant_engine.cpp_quant_backend`` import path is
not used here.
"""

from __future__ import annotations

import warnings
from typing import Any

from researchos.core.timestamp import utc_now
from researchos.quant_engine.capabilities import (
    QUANT_OPERATIONS,
    BackendCapabilities,
)
from researchos.quant_engine.interface import QuantComputationInterface
from researchos.quant_engine.models import (
    CalculationVersion,
    SimulationRequest,
    SimulationResult,
)
from researchos.quant_engine.performance import compute_performance_analytics

CALCULATION_V1 = CalculationVersion.CALCULATION_V1

# Periods per year used by ResearchOS annualisation (CALCULATION_V1).
_PERIODS_PER_YEAR = 252


def _require_v1(calculation_version: CalculationVersion) -> None:
    if calculation_version != CALCULATION_V1:
        raise ValueError(f"Unsupported calculation version: {calculation_version}")


def _get_native_backend_class() -> Any:
    """
    Resolve the compiled C++ backend class through the native module loader.

    ``native_module()`` is the canonical bridge between the Python package and
    the compiled extension. Keeping this resolution in one helper prevents
    drift between availability checks and adapter construction.
    """
    from cpp_quant_engine.backend import native_module

    return native_module().CppQuantBackend


def has_cpp_engine() -> bool:
    """Return True if the compiled C++ quant engine is importable."""
    try:
        _get_native_backend_class()
        return True
    except (ImportError, AttributeError, OSError):
        return False


def get_cpp_engine_version() -> str | None:
    """Return the C++ engine version string, or None if unavailable."""
    try:
        backend_class = _get_native_backend_class()
        return str(backend_class().get_version())
    except (ImportError, AttributeError, OSError):
        return None


class CppQuantAdapter(QuantComputationInterface):
    """
    ResearchOS computation backend backed by the compiled C++20 quant engine.

    Drop-in replacement for ``PythonQuantBackend``. Numerical computation is
    delegated to C++ when available. Python remains the fallback and ResearchOS
    reference implementation for performance analytics.
    """

    def __init__(self) -> None:
        self._cpp_backend = None
        self._fallback = None

        try:
            backend_class = _get_native_backend_class()
            self._cpp_backend = backend_class()
        except (ImportError, AttributeError, OSError) as exc:
            warnings.warn(
                f"C++ Quant Engine not available ({exc}). Falling back to PythonQuantBackend.",
                stacklevel=2,
            )

            from researchos.quant_engine.backend import PythonQuantBackend

            self._fallback = PythonQuantBackend()

    # ── Identity / availability ──────────────────────────────────────────────

    @property
    def is_cpp(self) -> bool:
        """True when the compiled C++ engine is active (no fallback)."""
        return self._cpp_backend is not None

    @property
    def _backend(self) -> Any:
        """The active computation delegate."""
        if self._cpp_backend is not None:
            return self._cpp_backend

        if self._fallback is not None:
            return self._fallback

        raise RuntimeError("No backend available")

    def get_version(self) -> str:
        """Return the C++ engine version, or 'python_fallback' if unavailable."""
        if self._cpp_backend is not None:
            return str(self._backend.get_version())

        return "python_fallback"

    def capabilities(self) -> BackendCapabilities:
        """Advertise the C++ adapter's certified capability declaration."""
        return BackendCapabilities(
            backend_name="CppQuantAdapter",
            version=self.get_version(),
            supported_operations=QUANT_OPERATIONS,
            deterministic=True,
            stateless=True,
            no_timestamps=True,
            no_randomness=True,
            explicit_typing=True,
        )

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _call(self, fn: Any, *args: Any) -> Any:
        """
        Invoke a backend method.

        The legacy/native C++ shim can raise RuntimeError for validation
        failures. Translate those to ValueError to honor the
        QuantComputationInterface contract.
        """
        try:
            return fn(*args)
        except RuntimeError as exc:
            raise ValueError(str(exc)) from None

    @staticmethod
    def _normalize_statistics(statistics: dict[str, Any]) -> dict[str, Any]:
        out = dict(statistics)

        if "count" in out:
            out["count"] = int(out["count"])

        return out

    @staticmethod
    def _normalize_metrics(metrics: dict[str, Any]) -> dict[str, float]:
        out: dict[str, float] = {key: float(value) for key, value in metrics.items()}

        if "max_drawdown" in out:
            out["max_drawdown"] = round(out["max_drawdown"], 8)

        if "max_drawdown" in out and "mean_return" in out and out["max_drawdown"] != 0.0:
            out["calmar_ratio"] = out["mean_return"] * _PERIODS_PER_YEAR / abs(out["max_drawdown"])

        return out

    @staticmethod
    def _normalize_drawdown(drawdown: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}

        if "max_drawdown" in drawdown:
            out["max_drawdown"] = float(drawdown["max_drawdown"])

        if "max_drawdown_pct" in drawdown:
            out["max_drawdown_pct"] = float(drawdown["max_drawdown_pct"])

        if "recovery_period" in drawdown:
            out["recovery_period"] = int(drawdown["recovery_period"])

        return out

    # ── Returns ───────────────────────────────────────────────────────────────

    def calculate_returns(
        self,
        prices: list[float],
        return_type: str = "percentage",
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> list[float]:
        _require_v1(calculation_version)

        if len(prices) < 2:
            raise ValueError(f"Need at least 2 prices to calculate returns, got {len(prices)}")

        if return_type not in ("absolute", "percentage", "log"):
            raise ValueError(f"Unrecognized return_type '{return_type}'. Expected 'absolute', 'percentage', or 'log'.")

        return list(
            self._call(
                self._backend.calculate_returns,
                prices,
                return_type,
            )
        )

    # ── Volatility ────────────────────────────────────────────────────────────

    def calculate_volatility(
        self,
        returns: list[float],
        method: str = "standard_deviation",
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> float:
        _require_v1(calculation_version)

        if not returns:
            raise ValueError("Cannot compute volatility on empty dataset")

        if method not in ("standard_deviation", "rolling", "change"):
            raise ValueError(f"Unrecognized method '{method}'. Expected 'standard_deviation', 'rolling', or 'change'.")

        return float(
            self._call(
                self._backend.calculate_volatility,
                returns,
                method,
            )
        )

    # ── Drawdown ──────────────────────────────────────────────────────────────

    def calculate_drawdown(
        self,
        equity_curve: list[float],
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> dict[str, Any]:
        _require_v1(calculation_version)

        if len(equity_curve) < 2:
            raise ValueError(f"Need at least 2 equity values, got {len(equity_curve)}")

        return self._normalize_drawdown(
            dict(
                self._call(
                    self._backend.calculate_drawdown,
                    equity_curve,
                )
            )
        )

    # ── Statistics ────────────────────────────────────────────────────────────

    def calculate_statistics(
        self,
        returns: list[float],
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> dict[str, Any]:
        _require_v1(calculation_version)

        if not returns:
            raise ValueError("Cannot compute statistics on empty dataset")

        return self._normalize_statistics(
            dict(
                self._call(
                    self._backend.calculate_statistics,
                    returns,
                )
            )
        )

    # ── Metrics ────────────────────────────────────────────────────────────────

    def calculate_metrics(
        self,
        returns: list[float],
        equity_curve: list[float],
        risk_free_rate: float = 0.0,
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> dict[str, float]:
        _require_v1(calculation_version)

        if not returns:
            raise ValueError("Cannot compute statistics on empty dataset")

        if len(returns) < 2:
            raise ValueError(f"Insufficient samples: need at least 2, got {len(returns)}")

        if len(equity_curve) < 2:
            raise ValueError(f"Need at least 2 equity values, got {len(equity_curve)}")

        raw = dict(
            self._call(
                self._backend.calculate_metrics,
                returns,
                equity_curve,
                risk_free_rate,
            )
        )

        return self._normalize_metrics(raw)

    # ── Performance Analytics ─────────────────────────────────────────────────

    def calculate_performance_analytics(
        self,
        returns: list[float],
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> dict[str, Any]:
        return compute_performance_analytics(
            returns,
            calculation_version,
        )

    # ── Regression ────────────────────────────────────────────────────────────
    #
    # These delegate to the compiled C++ Regression module via the native shim.
    # They are pure numerical research analytics — NOT trading logic, signals,
    # or prediction.

    def regression_slope(
        self,
        y: list[float],
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> float:
        _require_v1(calculation_version)

        if len(y) < 2:
            raise ValueError("need at least 2 observations for regression slope")

        return float(
            self._call(
                self._backend.regression_slope,
                y,
            )
        )

    def regression_intercept(
        self,
        y: list[float],
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> float:
        _require_v1(calculation_version)

        if len(y) < 2:
            raise ValueError("need at least 2 observations for regression intercept")

        return float(
            self._call(
                self._backend.regression_intercept,
                y,
            )
        )

    def regression_correlation(
        self,
        x: list[float],
        y: list[float],
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> float:
        _require_v1(calculation_version)

        if len(x) != len(y):
            raise ValueError("x and y size mismatch")

        if len(x) < 2:
            raise ValueError("need at least 2 observations for regression")

        return float(
            self._call(
                self._backend.regression_correlation,
                x,
                y,
            )
        )

    def regression_r_squared(
        self,
        x: list[float],
        y: list[float],
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> float:
        _require_v1(calculation_version)

        if len(x) != len(y):
            raise ValueError("x and y size mismatch")

        if len(x) < 2:
            raise ValueError("need at least 2 observations for regression")

        return float(
            self._call(
                self._backend.regression_r_squared,
                x,
                y,
            )
        )

    def regression_standard_error(
        self,
        x: list[float],
        y: list[float],
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> float:
        _require_v1(calculation_version)

        if len(x) != len(y):
            raise ValueError("x and y size mismatch")

        if len(x) < 2:
            raise ValueError("need at least 2 observations for regression")

        return float(
            self._call(
                self._backend.regression_standard_error,
                x,
                y,
            )
        )

    # ── Rolling statistics ────────────────────────────────────────────────────

    def rolling_mean(
        self,
        data: list[float],
        window: int,
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> list[float]:
        _require_v1(calculation_version)

        if window <= 0:
            raise ValueError("window must be > 0")

        if len(data) < window:
            raise ValueError("window size exceeds data length")

        return list(
            self._call(
                self._backend.rolling_mean,
                data,
                window,
            )
        )

    def rolling_volatility_series(
        self,
        data: list[float],
        window: int,
        ddof: int = 1,
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> list[float]:
        _require_v1(calculation_version)

        if window <= 0:
            raise ValueError("window must be > 0")

        if len(data) < window:
            raise ValueError("window size exceeds data length")

        if ddof < 0 or ddof >= window:
            raise ValueError("ddof must be in [0, window)")

        return list(
            self._call(
                self._backend.rolling_volatility_series_ext,
                data,
                window,
                ddof,
            )
        )

    def rolling_variance_series(
        self,
        data: list[float],
        window: int,
        ddof: int = 1,
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> list[float]:
        _require_v1(calculation_version)

        if window <= 0:
            raise ValueError("window must be > 0")

        if len(data) < window:
            raise ValueError("window size exceeds data length")

        if ddof < 0 or ddof >= window:
            raise ValueError("ddof must be in [0, window)")

        return list(
            self._call(
                self._backend.rolling_variance_ext,
                data,
                window,
                ddof,
            )
        )

    # ── Simulation ────────────────────────────────────────────────────────────

    def run_simulation(
        self,
        request: SimulationRequest,
        dataset: Any,
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> SimulationResult:
        _require_v1(calculation_version)

        from researchos.quant_engine.backend import PythonQuantBackend

        prices = PythonQuantBackend()._extract_prices(dataset)

        if len(prices) < 2:
            raise ValueError(f"Need at least 2 prices for simulation, got {len(prices)}")

        # Provenance comes from the ResearchOS request, not the C++ hashes.
        input_hash = request.compute_input_hash()
        sim_id = f"sim_{input_hash[:16]}"

        initial_capital = request.parameters.get(
            "initial_capital",
            100000.0,
        )
        risk_free_rate = request.parameters.get(
            "risk_free_rate",
            0.0,
        )

        # Numerical work is performed by C++ primitives.
        # The monolithic legacy run_simulation is intentionally not used.
        returns = list(
            self._call(
                self._backend.calculate_returns,
                prices,
                "percentage",
            )
        )

        equity_curve = self._build_equity_curve(
            returns,
            initial_capital,
        )

        metrics = self._normalize_metrics(
            dict(
                self._call(
                    self._backend.calculate_metrics,
                    returns,
                    equity_curve,
                    risk_free_rate,
                )
            )
        )

        statistics = self._normalize_statistics(
            dict(
                self._call(
                    self._backend.calculate_statistics,
                    returns,
                )
            )
        )

        performance = compute_performance_analytics(
            returns,
            calculation_version,
        )

        result = SimulationResult(
            simulation_id=sim_id,
            dataset_reference=request.dataset_reference,
            dataset_version=request.dataset_version,
            calculation_version=calculation_version,
            parameters=dict(request.parameters),
            start_time=request.start_time,
            end_time=request.end_time,
            input_hash=input_hash,
            execution_timestamp=utc_now().isoformat(),
            returns=returns,
            equity_curve=equity_curve,
            metrics=metrics,
            statistics=statistics,
            performance=performance,
        )

        result.result_hash = result.compute_result_hash()

        return result

    @staticmethod
    def _build_equity_curve(
        returns: list[float],
        initial_capital: float,
    ) -> list[float]:
        """Build an equity curve from percentage returns."""
        equity = [initial_capital]

        for r in returns:
            equity.append(equity[-1] * (1.0 + r))

        return equity


def create_cpp_router():
    """
    Create a backend router with C++ backend registered.

    Compatibility factory for integration tests and external callers.
    """
    from .backend import PythonQuantBackend
    from .router import BackendRouter

    router = BackendRouter(reference_backend=PythonQuantBackend())

    register_cpp_backend(router)

    return router


def register_cpp_backend(router=None, force=False):
    """
    Register C++ quant backend into BackendRouter.

    Compatibility API for Phase 4 integration tests.
    """
    adapter = CppQuantAdapter()

    if router is not None:
        router.register(adapter)

    return adapter
