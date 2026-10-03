"""
Python integration tests for the C++ Quant Acceleration Engine.

Tests:
    - C++ backend vs Python backend identical results
    - Serialization compatibility
    - Experiment Framework integration
    - SimulationResult consistency
    - Performance benchmark

Run with:
    python -m pytest cpp_quant_engine/tests/test_python_integration.py -v
"""

import math

import pytest

from researchos.engines.quant.backend import PythonQuantBackend
from researchos.engines.quant.cpp_backend import CppQuantAdapter, has_cpp_engine
from researchos.engines.quant.models import (
    CalculationVersion,
    SimulationRequest,
    SimulationResult,
)
from researchos.engines.quant.simulation import HistoricalSimulationEngine

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def python_backend():
    return PythonQuantBackend()


@pytest.fixture
def cpp_backend():
    """Require the compiled C++ backend; never silently substitute Python."""
    if not has_cpp_engine():
        pytest.fail(
            "C++ Quant Engine is unavailable; refusing to run integration tests against Python fallback."
        )
    backend = CppQuantAdapter()
    if not backend.is_cpp:
        pytest.fail("C++ Quant Engine is unavailable; refusing Python fallback.")
    return backend


@pytest.fixture
def sample_prices():
    return [
        100.0,
        102.0,
        101.0,
        105.0,
        103.0,
        107.0,
        106.0,
        110.0,
        108.0,
        112.0,
        111.0,
        115.0,
        113.0,
        117.0,
        116.0,
        120.0,
        118.0,
        122.0,
        121.0,
        125.0,
        123.0,
        127.0,
        126.0,
        130.0,
        128.0,
        132.0,
        131.0,
        135.0,
        133.0,
        137.0,
    ]


@pytest.fixture
def sample_returns(sample_prices):
    returns = []
    for i in range(1, len(sample_prices)):
        returns.append((sample_prices[i] - sample_prices[i - 1]) / sample_prices[i - 1])
    return returns


@pytest.fixture
def sample_equity_curve(sample_returns):
    equity = [100000.0]
    for r in sample_returns:
        equity.append(equity[-1] * (1.0 + r))
    return equity


# ── Backend Comparison Tests ────────────────────────────────────────────────


def test_returns_identical(python_backend, cpp_backend, sample_prices):
    """C++ and Python backends must produce identical returns."""
    for return_type in ["absolute", "percentage", "log"]:
        py_result = python_backend.calculate_returns(sample_prices, return_type)
        cpp_result = cpp_backend.calculate_returns(sample_prices, return_type)

        assert len(py_result) == len(cpp_result)
        for i in range(len(py_result)):
            assert abs(py_result[i] - cpp_result[i]) < 1e-12, f"Mismatch at {i} for return_type={return_type}: {py_result[i]} vs {cpp_result[i]}"


def test_volatility_identical(python_backend, cpp_backend, sample_returns):
    """C++ and Python backends must produce identical volatility."""
    # Standard deviation
    py_vol = python_backend.calculate_volatility(sample_returns, "standard_deviation")
    cpp_vol = cpp_backend.calculate_volatility(sample_returns, "standard_deviation")
    assert abs(py_vol - cpp_vol) < 1e-12, f"Volatility mismatch: {py_vol} vs {cpp_vol}"

    # Rolling
    py_rolling = python_backend.calculate_volatility(sample_returns, "rolling")
    cpp_rolling = cpp_backend.calculate_volatility(sample_returns, "rolling")
    assert abs(py_rolling - cpp_rolling) < 1e-12, f"Rolling vol mismatch: {py_rolling} vs {cpp_rolling}"


def test_drawdown_identical(python_backend, cpp_backend, sample_equity_curve):
    """C++ and Python backends must produce identical drawdown metrics."""
    py_dd = python_backend.calculate_drawdown(sample_equity_curve)
    cpp_dd = cpp_backend.calculate_drawdown(sample_equity_curve)

    for key in py_dd:
        assert abs(py_dd[key] - cpp_dd[key]) < 1e-10, f"Drawdown mismatch for {key}: {py_dd[key]} vs {cpp_dd[key]}"


def test_statistics_identical(python_backend, cpp_backend, sample_returns):
    """C++ and Python backends must produce identical statistics."""
    py_stats = python_backend.calculate_statistics(sample_returns)
    cpp_stats = cpp_backend.calculate_statistics(sample_returns)

    for key in py_stats:
        if key in ("count",):
            continue  # int vs float
        assert abs(py_stats[key] - cpp_stats[key]) < 1e-10, f"Statistics mismatch for {key}: {py_stats[key]} vs {cpp_stats[key]}"


def test_metrics_identical(python_backend, cpp_backend, sample_returns, sample_equity_curve):
    """C++ and Python backends must produce identical performance metrics."""
    py_metrics = python_backend.calculate_metrics(sample_returns, sample_equity_curve, 0.0)
    cpp_metrics = cpp_backend.calculate_metrics(sample_returns, sample_equity_curve, 0.0)

    for key in py_metrics:
        py_val = py_metrics[key]
        cpp_val = cpp_metrics[key]

        # Handle inf values
        if math.isinf(py_val) and math.isinf(cpp_val):
            continue

        assert abs(py_val - cpp_val) < 1e-10, f"Metrics mismatch for {key}: {py_val} vs {cpp_val}"


def test_performance_analytics_identical(python_backend, cpp_backend, sample_returns):
    """C++ and Python backends must produce identical performance analytics."""
    py_perf = python_backend.calculate_performance_analytics(sample_returns)
    cpp_perf = cpp_backend.calculate_performance_analytics(sample_returns)

    for key in py_perf:
        if key in ("total_returns", "max_consecutive_wins", "max_consecutive_losses"):
            continue  # int fields
        py_val = py_perf[key]
        cpp_val = cpp_perf[key]

        if math.isinf(py_val) and math.isinf(cpp_val):
            continue

        assert abs(py_val - cpp_val) < 1e-10, f"Performance mismatch for {key}: {py_val} vs {cpp_val}"


# ── Deterministic Results Tests ─────────────────────────────────────────────


def test_deterministic_returns(cpp_backend, sample_prices):
    """C++ backend must produce deterministic results."""
    r1 = cpp_backend.calculate_returns(sample_prices, "percentage")
    r2 = cpp_backend.calculate_returns(sample_prices, "percentage")
    assert r1 == r2


def test_deterministic_statistics(cpp_backend, sample_returns):
    """C++ backend statistics must be deterministic."""
    s1 = cpp_backend.calculate_statistics(sample_returns)
    s2 = cpp_backend.calculate_statistics(sample_returns)
    assert s1 == s2


def test_deterministic_metrics(cpp_backend, sample_returns, sample_equity_curve):
    """C++ backend metrics must be deterministic."""
    m1 = cpp_backend.calculate_metrics(sample_returns, sample_equity_curve, 0.0)
    m2 = cpp_backend.calculate_metrics(sample_returns, sample_equity_curve, 0.0)
    assert m1 == m2


# ── Edge Case Tests ─────────────────────────────────────────────────────────


def test_empty_returns_raises(cpp_backend):
    """C++ backend must raise on empty data."""
    with pytest.raises((ValueError, RuntimeError)):
        cpp_backend.calculate_volatility([], "standard_deviation")


def test_single_price_raises(cpp_backend):
    """C++ backend must raise on single price."""
    with pytest.raises((ValueError, RuntimeError)):
        cpp_backend.calculate_returns([100.0], "percentage")


def test_zero_variance_metrics(cpp_backend):
    """C++ backend must handle zero variance gracefully."""
    returns = [0.01, 0.01, 0.01, 0.01, 0.01]
    equity = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
    metrics = cpp_backend.calculate_metrics(returns, equity, 0.0)
    assert metrics["sharpe_ratio"] == 0.0


# ── Simulation Consistency Tests ────────────────────────────────────────────


def test_simulation_identical_results(python_backend, cpp_backend, sample_prices):
    """C++ and Python simulations must produce identical results."""
    request = SimulationRequest(
        dataset_reference="TEST",
        dataset_version="1.0.0",
        calculation_version=CalculationVersion.CALCULATION_V1,
        start_time="2020-01-01",
        end_time="2020-12-31",
        parameters={"initial_capital": 100000.0, "risk_free_rate": 0.0},
        seed=42,
    )

    py_result = python_backend.run_simulation(request, sample_prices)
    cpp_result = cpp_backend.run_simulation(request, sample_prices)

    # Compare returns
    for i in range(len(py_result.returns)):
        assert abs(py_result.returns[i] - cpp_result.returns[i]) < 1e-12, f"Return mismatch at {i}: {py_result.returns[i]} vs {cpp_result.returns[i]}"

    # Compare equity curves
    for i in range(len(py_result.equity_curve)):
        assert abs(py_result.equity_curve[i] - cpp_result.equity_curve[i]) < 1e-10, f"Equity mismatch at {i}: {py_result.equity_curve[i]} vs {cpp_result.equity_curve[i]}"

    # Compare metrics
    for key in py_result.metrics:
        py_val = py_result.metrics[key]
        cpp_val = cpp_result.metrics[key]
        if math.isinf(py_val) and math.isinf(cpp_val):
            continue
        assert abs(py_val - cpp_val) < 1e-10, f"Metric mismatch for {key}: {py_val} vs {cpp_val}"


def test_simulation_deterministic_cpp(cpp_backend, sample_prices):
    """C++ simulation must be deterministic."""
    request = SimulationRequest(
        dataset_reference="DETERM_TEST",
        parameters={"initial_capital": 100000.0, "risk_free_rate": 0.0},
        seed=42,
    )

    r1 = cpp_backend.run_simulation(request, sample_prices)
    r2 = cpp_backend.run_simulation(request, sample_prices)

    assert r1.input_hash == r2.input_hash
    assert r1.result_hash == r2.result_hash
    assert r1.returns == r2.returns
    assert r1.equity_curve == r2.equity_curve
    assert r1.metrics == r2.metrics


# ── Experiment Framework Integration ────────────────────────────────────────


def test_experiment_framework_integration(cpp_backend, sample_prices):
    """C++ backend must work with HistoricalSimulationEngine."""
    engine = HistoricalSimulationEngine()
    engine.set_backend(cpp_backend)

    request = SimulationRequest(
        dataset_reference="EXP_TEST",
        parameters={"initial_capital": 100000.0, "risk_free_rate": 0.0},
        seed=42,
    )

    result = engine.replay(request, sample_prices)
    assert isinstance(result, SimulationResult)
    assert len(result.returns) == len(sample_prices) - 1
    assert len(result.equity_curve) == len(sample_prices)
    assert "sharpe_ratio" in result.metrics
    assert "mean" in result.statistics
    assert result.result_hash is not None


# ── Serialization Compatibility ─────────────────────────────────────────────


def test_serialization_roundtrip(cpp_backend, sample_prices):
    """SimulationResult from C++ backend must be serializable."""
    request = SimulationRequest(
        dataset_reference="SERIAL_TEST",
        parameters={"initial_capital": 100000.0},
        seed=42,
    )

    result = cpp_backend.run_simulation(request, sample_prices)

    # to_dict
    d = result.to_dict()
    assert isinstance(d, dict)
    assert "simulation_id" in d
    assert "metrics" in d
    assert "statistics" in d
    assert "returns" in d

    # from_dict roundtrip
    restored = SimulationResult.from_dict(d)
    assert restored.simulation_id == result.simulation_id
    assert restored.result_hash == result.result_hash
    assert restored.returns == result.returns
    assert restored.metrics == result.metrics
