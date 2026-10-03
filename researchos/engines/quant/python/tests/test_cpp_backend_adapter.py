"""Tests for CppQuantAdapter — the ResearchOS QuantComputationInterface backed by C++.

Covers: interface conformance, C++ delegation, ResearchOS schema normalization,
validation contract (ValueError semantics matching PythonQuantBackend),
fallback behavior, determinism, serialization round-trips, and drop-in use via
HistoricalSimulationEngine.
"""

import math
import sys

import pytest
from researchos.engines.quant.cpp_backend import (
    CppQuantAdapter,
    get_cpp_engine_version,
    has_cpp_engine,
)

from researchos.engines.quant.backend import PythonQuantBackend
from researchos.engines.quant.interface import QuantComputationInterface
from researchos.engines.quant.models import CalculationVersion, SimulationRequest
from researchos.engines.quant.simulation import HistoricalSimulationEngine

_V1 = CalculationVersion.CALCULATION_V1


def make_prices(n, base=100.0):
    return [base + 30.0 * math.sin(i / 4.0) + 0.5 * (i % 7) for i in range(n)]


def make_request(**params):
    merged = {"initial_capital": 100000.0, "risk_free_rate": 0.0}
    merged.update(params)
    return SimulationRequest(
        dataset_reference="XAU/USD:TEST",
        dataset_version="1.0.0",
        calculation_version=_V1,
        start_time="2026-01-01T00:00:00",
        end_time="2026-01-31T00:00:00",
        parameters=merged,
        seed=42,
    )


@pytest.fixture(scope="module")
def adapter():
    if not has_cpp_engine():
        pytest.fail(
            "C++ Quant Engine is unavailable; this adapter suite must fail rather than skip or fallback."
        )
    backend = CppQuantAdapter()
    if not backend.is_cpp:
        pytest.fail("C++ Quant Engine is unavailable; refusing Python fallback in C++ adapter suite.")
    return backend


@pytest.fixture(scope="module")
def python_backend():
    return PythonQuantBackend()


@pytest.fixture(scope="module")
def prices():
    return make_prices(40)


class TestCppQuantAdapterCore:
    def test_implements_interface(self, adapter):
        assert isinstance(adapter, QuantComputationInterface)

    def test_is_cpp_when_engine_available(self, adapter):
        assert adapter.is_cpp is True

    def test_get_version_semver(self, adapter):
        parts = adapter.get_version().split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_has_cpp_engine_helper(self):
        assert has_cpp_engine() is True
        version = get_cpp_engine_version()
        assert version is not None
        assert len(version.split(".")) == 3

    def test_constructor_matches_python_backend_signature(self):
        # Both backends are constructed with no arguments (drop-in swap).
        PythonQuantBackend()
        CppQuantAdapter()

    def test_deterministic_across_runs(self, adapter, prices):
        request = make_request()
        a = adapter.run_simulation(request, prices)
        b = adapter.run_simulation(request, prices)
        assert a.result_hash == b.result_hash
        assert a.returns == b.returns
        assert a.metrics == b.metrics

    def test_result_hash_self_consistent(self, adapter, prices):
        result = adapter.run_simulation(make_request(), prices)
        assert result.result_hash == result.compute_result_hash()


class TestCppQuantAdapterReturns:
    def test_matches_python_percentage(self, adapter, python_backend, prices):
        assert adapter.calculate_returns(prices) == python_backend.calculate_returns(prices)

    def test_matches_python_absolute(self, adapter, python_backend, prices):
        assert adapter.calculate_returns(prices, "absolute") == python_backend.calculate_returns(prices, "absolute")

    def test_matches_python_log(self, adapter, python_backend, prices):
        assert adapter.calculate_returns(prices, "log") == python_backend.calculate_returns(prices, "log")

    def test_length(self, adapter, prices):
        assert len(adapter.calculate_returns(prices)) == len(prices) - 1

    def test_short_prices_raise(self, adapter, python_backend):
        with pytest.raises(ValueError):
            adapter.calculate_returns([100.0])
        with pytest.raises(ValueError):
            python_backend.calculate_returns([100.0])

    def test_unknown_return_type_raises(self, adapter, python_backend, prices):
        with pytest.raises(ValueError):
            adapter.calculate_returns(prices, "bogus")
        with pytest.raises(ValueError):
            python_backend.calculate_returns(prices, "bogus")


class TestCppQuantAdapterVolatility:
    def test_standard_deviation_matches(self, adapter, python_backend, prices):
        rets = adapter.calculate_returns(prices)
        assert adapter.calculate_volatility(rets) == pytest.approx(python_backend.calculate_volatility(rets), rel=1e-9)

    def test_rolling_matches(self, adapter, python_backend):
        rets = adapter.calculate_returns(make_prices(60))
        assert adapter.calculate_volatility(rets, "rolling") == pytest.approx(python_backend.calculate_volatility(rets, "rolling"), rel=1e-9)

    def test_change_matches(self, adapter, python_backend):
        rets = adapter.calculate_returns(make_prices(60))
        assert adapter.calculate_volatility(rets, "change") == pytest.approx(python_backend.calculate_volatility(rets, "change"), rel=1e-9)

    def test_empty_raises(self, adapter, python_backend):
        with pytest.raises(ValueError):
            adapter.calculate_volatility([])
        with pytest.raises(ValueError):
            python_backend.calculate_volatility([])

    def test_unknown_method_raises(self, adapter, python_backend, prices):
        rets = adapter.calculate_returns(prices)
        with pytest.raises(ValueError):
            adapter.calculate_volatility(rets, "bogus")
        with pytest.raises(ValueError):
            python_backend.calculate_volatility(rets, "bogus")


class TestCppQuantAdapterDrawdown:
    def test_normalized_schema(self, adapter, prices):
        returns = adapter.calculate_returns(prices)
        equity = [100000.0]
        for r in returns:
            equity.append(equity[-1] * (1.0 + r))
        dd = adapter.calculate_drawdown(equity)
        assert set(dd) == {"max_drawdown", "max_drawdown_pct", "recovery_period"}
        assert isinstance(dd["recovery_period"], int)

    def test_matches_python(self, adapter, python_backend, prices):
        returns = adapter.calculate_returns(prices)
        equity = [100000.0]
        for r in returns:
            equity.append(equity[-1] * (1.0 + r))
        assert adapter.calculate_drawdown(equity) == python_backend.calculate_drawdown(equity)

    def test_short_raises(self, adapter, python_backend):
        with pytest.raises(ValueError):
            adapter.calculate_drawdown([100.0])
        with pytest.raises(ValueError):
            python_backend.calculate_drawdown([100.0])


class TestCppQuantAdapterStatistics:
    def test_count_is_int(self, adapter, prices):
        stats = adapter.calculate_statistics(adapter.calculate_returns(prices))
        assert stats["count"] == len(prices) - 1
        assert isinstance(stats["count"], int)

    def test_matches_python(self, adapter, python_backend, prices):
        rets = adapter.calculate_returns(prices)
        py_stats = python_backend.calculate_statistics(rets)
        cpp_stats = adapter.calculate_statistics(rets)
        assert set(py_stats) == set(cpp_stats)
        for key in py_stats:
            if key == "count":
                assert py_stats[key] == cpp_stats[key]
            else:
                assert cpp_stats[key] == pytest.approx(py_stats[key], rel=1e-9, abs=1e-12)

    def test_empty_raises(self, adapter, python_backend):
        with pytest.raises(ValueError):
            adapter.calculate_statistics([])
        with pytest.raises(ValueError):
            python_backend.calculate_statistics([])


class TestCppQuantAdapterMetrics:
    def test_schema_keys(self, adapter, prices):
        rets = adapter.calculate_returns(prices)
        equity = [100000.0]
        for r in rets:
            equity.append(equity[-1] * (1.0 + r))
        metrics = adapter.calculate_metrics(rets, equity, 0.0)
        expected = {
            "total_return",
            "mean_return",
            "std_return",
            "downside_deviation",
            "max_drawdown",
            "sharpe_ratio",
            "sortino_ratio",
            "calmar_ratio",
            "profit_factor",
            "win_rate",
            "annualised_return",
            "annualised_volatility",
        }
        assert set(metrics) == expected

    def test_max_drawdown_rounded(self, adapter, python_backend, prices):
        rets = adapter.calculate_returns(prices)
        equity = [100000.0]
        for r in rets:
            equity.append(equity[-1] * (1.0 + r))
        assert adapter.calculate_metrics(rets, equity, 0.0)["max_drawdown"] == python_backend.calculate_metrics(rets, equity, 0.0)["max_drawdown"]
        assert isinstance(adapter.calculate_metrics(rets, equity, 0.0)["max_drawdown"], float)

    def test_calmar_consistent_with_rounded_drawdown(self, adapter, prices):
        rets = adapter.calculate_returns(prices)
        equity = [100000.0]
        for r in rets:
            equity.append(equity[-1] * (1.0 + r))
        metrics = adapter.calculate_metrics(rets, equity, 0.0)
        expected = metrics["mean_return"] * 252.0 / abs(metrics["max_drawdown"])
        assert metrics["calmar_ratio"] == pytest.approx(expected, rel=1e-12)

    def test_matches_python(self, adapter, python_backend, prices):
        rets = adapter.calculate_returns(prices)
        equity = [100000.0]
        for r in rets:
            equity.append(equity[-1] * (1.0 + r))
        for rf in (0.0, 0.05):
            py_metrics = python_backend.calculate_metrics(rets, equity, rf)
            cpp_metrics = adapter.calculate_metrics(rets, equity, rf)
            assert set(py_metrics) == set(cpp_metrics)
            for key in py_metrics:
                assert cpp_metrics[key] == pytest.approx(py_metrics[key], rel=1e-9, abs=1e-12)

    def test_empty_raises(self, adapter, python_backend):
        with pytest.raises(ValueError):
            adapter.calculate_metrics([], [100.0, 101.0])
        with pytest.raises(ValueError):
            python_backend.calculate_metrics([], [100.0, 101.0])


class TestCppQuantAdapterPerformance:
    def test_matches_python_exact(self, adapter, python_backend, prices):
        rets = adapter.calculate_returns(prices)
        assert adapter.calculate_performance_analytics(rets) == python_backend.calculate_performance_analytics(rets)

    def test_schema(self, adapter, prices):
        perf = adapter.calculate_performance_analytics(adapter.calculate_returns(prices))
        expected = {
            "win_rate",
            "loss_rate",
            "average_win",
            "average_loss",
            "win_loss_ratio",
            "profit_factor",
            "consistency",
            "max_consecutive_wins",
            "max_consecutive_losses",
            "total_returns",
            "net_return",
        }
        assert set(perf) == expected

    def test_empty_raises(self, adapter, python_backend):
        with pytest.raises(ValueError):
            adapter.calculate_performance_analytics([])
        with pytest.raises(ValueError):
            python_backend.calculate_performance_analytics([])


class TestCppQuantAdapterSimulation:
    def test_provenance(self, adapter, prices):
        request = make_request()
        result = adapter.run_simulation(request, prices)
        assert result.input_hash == request.compute_input_hash()
        assert result.simulation_id == f"sim_{result.input_hash[:16]}"
        assert result.dataset_reference == request.dataset_reference
        assert result.dataset_version == request.dataset_version
        assert result.calculation_version == request.calculation_version
        assert result.start_time == request.start_time
        assert result.end_time == request.end_time
        assert result.parameters == request.parameters
        assert result.execution_timestamp

    def test_shapes(self, adapter, prices):
        result = adapter.run_simulation(make_request(), prices)
        assert len(result.returns) == len(prices) - 1
        assert len(result.equity_curve) == len(prices)
        assert result.equity_curve[0] == pytest.approx(100000.0)

    def test_normalized_fields(self, adapter, prices):
        result = adapter.run_simulation(make_request(), prices)
        assert isinstance(result.statistics["count"], int)
        assert result.performance["total_returns"] == len(prices) - 1
        assert isinstance(result.performance["total_returns"], int)
        assert isinstance(result.performance["max_consecutive_wins"], int)

    def test_matches_python(self, adapter, python_backend, prices):
        request = make_request()
        py_result = python_backend.run_simulation(request, prices)
        cpp_result = adapter.run_simulation(request, prices)
        assert py_result.returns == cpp_result.returns
        assert py_result.equity_curve == cpp_result.equity_curve
        assert py_result.performance == cpp_result.performance
        assert py_result.input_hash == cpp_result.input_hash
        assert py_result.simulation_id == cpp_result.simulation_id
        for key in py_result.metrics:
            assert cpp_result.metrics[key] == pytest.approx(py_result.metrics[key], rel=1e-9, abs=1e-12)

    def test_custom_parameters(self, adapter, python_backend, prices):
        request = make_request(initial_capital=50000.0, risk_free_rate=0.05)
        py_result = python_backend.run_simulation(request, prices)
        cpp_result = adapter.run_simulation(request, prices)
        assert cpp_result.equity_curve[0] == pytest.approx(50000.0)
        assert cpp_result.metrics["max_drawdown"] == py_result.metrics["max_drawdown"]
        assert cpp_result.equity_curve == py_result.equity_curve

    def test_short_prices_raise(self, adapter, python_backend):
        request = make_request()
        with pytest.raises(ValueError):
            adapter.run_simulation(request, [100.0])
        with pytest.raises(ValueError):
            python_backend.run_simulation(request, [100.0])


class TestCppQuantAdapterVersions:
    @pytest.mark.parametrize(
        "call",
        [
            lambda b: b.calculate_returns([100.0, 101.0], "percentage", "CALCULATION_V2"),
            lambda b: b.calculate_volatility([0.01, 0.02], "standard_deviation", "CALCULATION_V2"),
            lambda b: b.calculate_drawdown([100.0, 101.0], "CALCULATION_V2"),
            lambda b: b.calculate_statistics([0.01, 0.02], "CALCULATION_V2"),
            lambda b: b.calculate_metrics([0.01, 0.02], [100.0, 101.0], 0.0, "CALCULATION_V2"),
            lambda b: b.calculate_performance_analytics([0.01, 0.02], "CALCULATION_V2"),
            lambda b: b.run_simulation(SimulationRequest(dataset_reference="T"), [100.0, 101.0], "CALCULATION_V2"),
        ],
    )
    def test_unsupported_version_raises(self, adapter, python_backend, call):
        with pytest.raises(ValueError):
            call(adapter)
        with pytest.raises(ValueError):
            call(python_backend)


class TestCppQuantAdapterSerialization:
    def test_round_trip(self, adapter, prices):
        from researchos.engines.quant.models import SimulationResult

        result = adapter.run_simulation(make_request(), prices)
        data = result.to_dict()

        restored = SimulationResult.from_dict(data)
        assert restored.to_dict() == data
        assert restored.compute_result_hash() == result.compute_result_hash()
        assert restored.result_hash == result.result_hash


class TestCppQuantAdapterEngineSwap:
    def test_drop_in_backend_swap(self, adapter, python_backend, prices):
        py_engine = HistoricalSimulationEngine(backend=python_backend)
        cpp_engine = HistoricalSimulationEngine(backend=adapter)

        request = make_request()
        py_result = py_engine.replay(request, prices)
        cpp_result = cpp_engine.replay(request, prices)

        assert cpp_engine.backend is adapter
        assert py_result.returns == cpp_result.returns
        assert py_result.input_hash == cpp_result.input_hash
        assert cpp_result.result_hash == cpp_result.compute_result_hash()

    def test_set_backend_swap(self, python_backend, adapter, prices):
        engine = HistoricalSimulationEngine()
        assert isinstance(engine.backend, PythonQuantBackend)
        engine.set_backend(adapter)
        assert engine.backend is adapter
        result = engine.replay(make_request(), prices)
        assert result.result_hash == result.compute_result_hash()


class TestCppQuantAdapterFallback:
    def test_fallback_when_cpp_unavailable(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "cpp_quant_engine.cpp_quant_backend", None)
        with pytest.warns(UserWarning):
            fallback = CppQuantAdapter()
        assert fallback.is_cpp is False
        assert fallback.get_version() == "python_fallback"

        prices = make_prices(10)
        request = make_request()
        result = fallback.run_simulation(request, prices)
        assert result.result_hash == result.compute_result_hash()
        assert len(result.returns) == len(prices) - 1

        # Behavior matches the reference Python backend.
        reference = PythonQuantBackend().run_simulation(request, prices)
        assert fallback.calculate_returns(prices) == reference.returns
