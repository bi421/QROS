"""Cross-backend parity tests: PythonQuantBackend vs CppQuantAdapter.

Covers: full parity reports (small + 100k prices), exact equality of returns /
equity / performance, tolerance-bounded equality of metrics / statistics,
ResearchOS normalization (int count, rounded max_drawdown, recomputed calmar),
input_hash / simulation_id / canonical result-hash parity, identical validation
behavior, serialization round-trips, and an opt-in 1M-price benchmark.

The perf test is gated behind the RESEARCHOS_PERF=1 environment variable.
"""

import math
import os
import time

import pytest
from researchos.engines.quant.cpp_backend import CppQuantAdapter, has_cpp_engine

from researchos.engines.quant.backend import PythonQuantBackend
from researchos.engines.quant.compatibility import (
    DEFAULT_TOLERANCES,
    canonical_result_hash,
    verify_backend_parity,
)
from researchos.engines.quant.interface import QuantComputationInterface
from researchos.engines.quant.models import CalculationVersion, SimulationRequest, SimulationResult

_V1 = CalculationVersion.CALCULATION_V1

# Minimum data length for rolling volatility / volatility change (window 21).
_ROLLING_MIN = 60


def make_prices(n: int, base: float = 100.0) -> list[float]:
    return [base + 30.0 * math.sin(i / 4.0) + 0.5 * (i % 7) for i in range(n)]


def make_request(**params) -> SimulationRequest:
    merged = {"initial_capital": 100000.0, "risk_free_rate": 0.0}
    merged.update(params)
    return SimulationRequest(
        dataset_reference="XAU/USD:PARITY",
        dataset_version="1.0.0",
        calculation_version=_V1,
        start_time="2026-01-01T00:00:00",
        end_time="2026-12-31T00:00:00",
        parameters=merged,
        seed=42,
        tags=["parity"],
    )


@pytest.fixture(scope="module")
def python_backend() -> PythonQuantBackend:
    return PythonQuantBackend()


@pytest.fixture(scope="module")
def cpp_backend() -> CppQuantAdapter:
    if not has_cpp_engine():
        pytest.fail(
            "C++ Quant Engine is unavailable; this parity suite must fail rather than skip or fallback."
        )
    backend = CppQuantAdapter()
    if not backend.is_cpp:
        pytest.fail("C++ Quant Engine is unavailable; refusing Python fallback in C++ parity suite.")
    return backend


def build_equity(returns: list[float], initial_capital: float = 100000.0) -> list[float]:
    equity = [initial_capital]
    for r in returns:
        equity.append(equity[-1] * (1.0 + r))
    return equity


class TestSmallParity:
    def test_full_parity(self, python_backend, cpp_backend):
        report = verify_backend_parity(python_backend, cpp_backend, make_prices(_ROLLING_MIN), make_request())
        assert report.matched is True
        assert report.hash_parity is True
        report.assert_matches()

    def test_returns_equity_bit_identical(self, python_backend, cpp_backend):
        request = make_request()
        py_result = python_backend.run_simulation(request, make_prices(_ROLLING_MIN))
        cpp_result = cpp_backend.run_simulation(request, make_prices(_ROLLING_MIN))
        assert py_result.returns == cpp_result.returns
        assert py_result.equity_curve == cpp_result.equity_curve

    def test_performance_exact(self, python_backend, cpp_backend):
        prices = make_prices(_ROLLING_MIN)
        py_result = python_backend.run_simulation(make_request(), prices)
        cpp_result = cpp_backend.run_simulation(make_request(), prices)
        assert py_result.performance == cpp_result.performance

    def test_statistics_count_int(self, python_backend, cpp_backend):
        prices = make_prices(_ROLLING_MIN)
        py_result = python_backend.run_simulation(make_request(), prices)
        cpp_result = cpp_backend.run_simulation(make_request(), prices)
        assert isinstance(py_result.statistics["count"], int)
        assert isinstance(cpp_result.statistics["count"], int)
        assert py_result.statistics["count"] == cpp_result.statistics["count"]

    def test_max_drawdown_normalized(self, python_backend, cpp_backend):
        prices = make_prices(_ROLLING_MIN)
        py_result = python_backend.run_simulation(make_request(), prices)
        cpp_result = cpp_backend.run_simulation(make_request(), prices)
        assert py_result.metrics["max_drawdown"] == pytest.approx(cpp_result.metrics["max_drawdown"], abs=0.0)
        # Both use the ResearchOS 8dp rounding of max_drawdown.
        assert cpp_result.metrics["max_drawdown"] == round(py_result.metrics["max_drawdown"], 8)

    def test_calmar_recomputed_from_rounded_drawdown(self, python_backend, cpp_backend):
        prices = make_prices(_ROLLING_MIN)
        py_result = python_backend.run_simulation(make_request(), prices)
        cpp_result = cpp_backend.run_simulation(make_request(), prices)
        assert cpp_result.metrics["calmar_ratio"] == pytest.approx(py_result.metrics["calmar_ratio"], rel=1e-12)

    def test_metrics_within_tolerance(self, python_backend, cpp_backend):
        prices = make_prices(_ROLLING_MIN)
        py_result = python_backend.run_simulation(make_request(), prices)
        cpp_result = cpp_backend.run_simulation(make_request(), prices)
        assert set(py_result.metrics) == set(cpp_result.metrics)
        for key in py_result.metrics:
            assert cpp_result.metrics[key] == pytest.approx(py_result.metrics[key], rel=1e-9, abs=1e-12)

    def test_input_hash_and_sim_id_match(self, python_backend, cpp_backend):
        prices = make_prices(_ROLLING_MIN)
        request = make_request()
        py_result = python_backend.run_simulation(request, prices)
        cpp_result = cpp_backend.run_simulation(request, prices)
        assert py_result.input_hash == cpp_result.input_hash
        assert py_result.input_hash == request.compute_input_hash()
        assert py_result.simulation_id == cpp_result.simulation_id

    def test_canonical_hash_parity(self, python_backend, cpp_backend):
        prices = make_prices(_ROLLING_MIN)
        py_result = python_backend.run_simulation(make_request(), prices)
        cpp_result = cpp_backend.run_simulation(make_request(), prices)
        assert canonical_result_hash(py_result) == canonical_result_hash(cpp_result)

    def test_result_hash_self_consistent_both(self, python_backend, cpp_backend):
        prices = make_prices(_ROLLING_MIN)
        assert python_backend.run_simulation(make_request(), prices).result_hash == (python_backend.run_simulation(make_request(), prices).compute_result_hash())
        cpp_result = cpp_backend.run_simulation(make_request(), prices)
        assert cpp_result.result_hash == cpp_result.compute_result_hash()

    def test_risk_free_rate_parity(self, python_backend, cpp_backend):
        prices = make_prices(_ROLLING_MIN)
        request = make_request(risk_free_rate=0.05)
        report = verify_backend_parity(python_backend, cpp_backend, prices, request)
        assert report.matched is True
        assert report.hash_parity is True

    def test_custom_initial_capital_parity(self, python_backend, cpp_backend):
        prices = make_prices(_ROLLING_MIN)
        request = make_request(initial_capital=250000.0, risk_free_rate=0.03)
        report = verify_backend_parity(python_backend, cpp_backend, prices, request)
        assert report.matched is True
        assert report.hash_parity is True

    def test_no_drawdown_series_parity(self, python_backend, cpp_backend):
        # Monotonic prices -> max_drawdown == 0 -> calmar == 0 (edge case).
        prices = [100.0 + 0.5 * i for i in range(_ROLLING_MIN)]
        report = verify_backend_parity(python_backend, cpp_backend, prices, make_request())
        assert report.matched is True
        assert report.hash_parity is True
        assert report.sections["metrics"].matched


class TestReport:
    def test_report_to_dict(self, python_backend, cpp_backend):
        report = verify_backend_parity(python_backend, cpp_backend, make_prices(_ROLLING_MIN), make_request())
        data = report.to_dict()
        assert data["matched"] is True
        assert data["hash_parity"] is True
        assert set(data["sections"]) == set(DEFAULT_TOLERANCES)
        for diff in data["field_diffs"]:
            assert diff["matched"] is True

    def test_report_versions(self, python_backend, cpp_backend):
        report = verify_backend_parity(python_backend, cpp_backend, make_prices(_ROLLING_MIN), make_request())
        assert report.backend_versions["cpp"].startswith("1.")
        assert report.backend_versions["python"] == "PythonQuantBackend"

    def test_assert_matches_raises_on_divergence(self, python_backend):
        class BrokenBackend(QuantComputationInterface):
            def __init__(self, delegate: QuantComputationInterface):
                self._delegate = delegate

            def get_version(self) -> str:
                return "broken"

            def calculate_returns(self, prices, return_type="percentage", calculation_version=_V1):
                return self._delegate.calculate_returns(prices, return_type, calculation_version)

            def calculate_volatility(self, returns, method="standard_deviation", calculation_version=_V1):
                return self._delegate.calculate_volatility(returns, method, calculation_version)

            def calculate_drawdown(self, equity_curve, calculation_version=_V1):
                return self._delegate.calculate_drawdown(equity_curve, calculation_version)

            def calculate_statistics(self, returns, calculation_version=_V1):
                stats = self._delegate.calculate_statistics(returns, calculation_version)
                stats["mean"] = stats["mean"] + 1.0
                return stats

            def calculate_metrics(self, returns, equity_curve, risk_free_rate=0.0, calculation_version=_V1):
                metrics = self._delegate.calculate_metrics(returns, equity_curve, risk_free_rate, calculation_version)
                metrics["sharpe_ratio"] = metrics["sharpe_ratio"] + 100.0
                return metrics

            def calculate_performance_analytics(self, returns, calculation_version=_V1):
                return self._delegate.calculate_performance_analytics(returns, calculation_version)

            def run_simulation(self, request, prices, calculation_version=_V1):
                result = self._delegate.run_simulation(request, prices, calculation_version)
                result.metrics = dict(result.metrics)
                result.metrics["sharpe_ratio"] = result.metrics["sharpe_ratio"] + 100.0
                result.statistics = dict(result.statistics)
                result.statistics["mean"] = result.statistics["mean"] + 1.0
                result.result_hash = result.compute_result_hash()
                return result

        report = verify_backend_parity(python_backend, BrokenBackend(python_backend), make_prices(_ROLLING_MIN), make_request())
        assert report.matched is False
        with pytest.raises(AssertionError):
            report.assert_matches()
        assert any(not d.matched for d in report.field_diffs)


class TestLargeParity:
    def test_100k_prices_parity(self, python_backend, cpp_backend):
        prices = make_prices(100_000)
        request = make_request()
        py_result = python_backend.run_simulation(request, prices)
        cpp_result = cpp_backend.run_simulation(request, prices)
        assert py_result.returns == cpp_result.returns
        assert py_result.equity_curve == cpp_result.equity_curve
        assert py_result.statistics["count"] == cpp_result.statistics["count"] == 99_999
        assert cpp_result.metrics["max_drawdown"] == py_result.metrics["max_drawdown"]
        assert cpp_result.result_hash == cpp_result.compute_result_hash()
        assert canonical_result_hash(py_result) == canonical_result_hash(cpp_result)


_RUN_PERF = os.environ.get("RESEARCHOS_PERF") == "1"


@pytest.mark.skipif(not _RUN_PERF, reason="set RESEARCHOS_PERF=1 to run the 1M-price benchmark")
class TestPerf:
    def test_1m_prices_parity_and_perf(self, python_backend, cpp_backend):
        prices = make_prices(1_000_000)
        request = make_request()

        t0 = time.perf_counter()
        py_result = python_backend.run_simulation(request, prices)
        py_elapsed = time.perf_counter() - t0

        t0 = time.perf_counter()
        cpp_result = cpp_backend.run_simulation(request, prices)
        cpp_elapsed = time.perf_counter() - t0

        # Correctness / parity at scale.
        assert py_result.returns == cpp_result.returns
        assert py_result.equity_curve == cpp_result.equity_curve
        assert cpp_result.result_hash == cpp_result.compute_result_hash()
        assert canonical_result_hash(py_result) == canonical_result_hash(cpp_result)

        # Generous wall-clock gate (environment thermal noise varies widely).
        assert cpp_elapsed < 45.0, f"C++ backend too slow: {cpp_elapsed:.2f}s"
        print(f"\n1M prices: python={py_elapsed:.2f}s cpp={cpp_elapsed:.2f}s speedup={py_elapsed / cpp_elapsed:.2f}x")


class TestValidationParity:
    def test_short_prices_raise_both(self, python_backend, cpp_backend):
        with pytest.raises(ValueError):
            python_backend.run_simulation(make_request(), [100.0])
        with pytest.raises(ValueError):
            cpp_backend.run_simulation(make_request(), [100.0])

    def test_empty_returns_raise_both(self, python_backend, cpp_backend):
        for method in (
            "calculate_statistics",
            "calculate_volatility",
            "calculate_performance_analytics",
        ):
            with pytest.raises(ValueError):
                getattr(python_backend, method)([])
            with pytest.raises(ValueError):
                getattr(cpp_backend, method)([])

    def test_short_metrics_raise_both(self, python_backend, cpp_backend):
        with pytest.raises(ValueError):
            python_backend.calculate_metrics([0.01], [100.0, 101.0])
        with pytest.raises(ValueError):
            cpp_backend.calculate_metrics([0.01], [100.0, 101.0])

    def test_unsupported_version_raises_both(self, python_backend, cpp_backend):
        with pytest.raises(ValueError):
            python_backend.run_simulation(make_request(), [100.0, 101.0], "CALCULATION_V2")
        with pytest.raises(ValueError):
            cpp_backend.run_simulation(make_request(), [100.0, 101.0], "CALCULATION_V2")

    def test_unknown_return_type_raises_both(self, python_backend, cpp_backend):
        with pytest.raises(ValueError):
            python_backend.calculate_returns([100.0, 101.0], "bogus")
        with pytest.raises(ValueError):
            cpp_backend.calculate_returns([100.0, 101.0], "bogus")


class TestSerializationParity:
    def test_round_trip_both_backends(self, python_backend, cpp_backend):
        prices = make_prices(_ROLLING_MIN)
        request = make_request()
        for backend in (python_backend, cpp_backend):
            result = backend.run_simulation(request, prices)
            data = result.to_dict()
            restored = SimulationResult.from_dict(data)
            assert restored.to_dict() == data
            assert restored.compute_result_hash() == result.compute_result_hash()

    def test_cross_backend_dict_schema_compatible(self, python_backend, cpp_backend):
        prices = make_prices(_ROLLING_MIN)
        request = make_request()
        py_data = python_backend.run_simulation(request, prices).to_dict()
        cpp_data = cpp_backend.run_simulation(request, prices).to_dict()
        assert set(py_data) == set(cpp_data)
        assert py_data["input_hash"] == cpp_data["input_hash"]
        assert py_data["simulation_id"] == cpp_data["simulation_id"]
        assert set(py_data["metrics"]) == set(cpp_data["metrics"])
        assert set(py_data["statistics"]) == set(cpp_data["statistics"])
        assert set(py_data["performance"]) == set(cpp_data["performance"])
