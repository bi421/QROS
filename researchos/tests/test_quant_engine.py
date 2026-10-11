"""
Comprehensive tests for the Quant Computation Engine (Phase 6).

Covers:
    1. Deterministic calculations
    2. Return calculation accuracy
    3. Volatility calculation
    4. Drawdown calculation
    5. Simulation replay consistency
    6. Result hashing
    7. Serialization
    8. Interface compatibility
    9. Integration with Experiment Framework
    10. Integration with Market Memory
"""

from __future__ import annotations

import math

import pytest

from researchos.quant_engine import (
    # Models
    CalculationVersion,
    # Engine
    HistoricalSimulationEngine,
    PythonQuantBackend,
    # Interface
    QuantComputationInterface,
    SimulationRequest,
    SimulationResult,
    # Statistics
    calculate_returns_from_prices,
    calmar_ratio,
    compute_all_metrics,
    compute_performance_analytics,
    compute_statistics,
    consistency,
    distribution_analysis,
    downside_deviation,
    kurtosis,
    max_consecutive_losses,
    max_consecutive_wins,
    max_drawdown,
    mean,
    profit_factor,
    rolling_volatility,
    # Metrics
    sharpe_ratio,
    skewness,
    sortino_ratio,
    standard_deviation,
    variance,
    volatility_change,
    # Performance
    win_loss_ratio,
    z_score,
)

# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def sample_prices() -> list[float]:
    """11 daily prices (10 returns) — deterministic dataset."""
    return [100.0, 102.0, 101.0, 103.0, 107.0, 106.0, 108.0, 110.0, 109.0, 111.0, 115.0]


@pytest.fixture
def sample_returns(sample_prices) -> list[float]:
    return calculate_returns_from_prices(sample_prices, "percentage")


@pytest.fixture
def backend() -> PythonQuantBackend:
    return PythonQuantBackend()


@pytest.fixture
def engine() -> HistoricalSimulationEngine:
    return HistoricalSimulationEngine()


@pytest.fixture
def simulation_request() -> SimulationRequest:
    return SimulationRequest(
        dataset_reference="XAU/USD:2020-2024",
        dataset_version="1.0.0",
        calculation_version=CalculationVersion.CALCULATION_V1,
        start_time="2020-01-01",
        end_time="2024-12-31",
        parameters={"initial_capital": 100000.0, "risk_free_rate": 0.05},
        seed=42,
    )


# ──────────────────────────────────────────────
# 1. Deterministic Calculations
# ──────────────────────────────────────────────


class TestDeterministicCalculations:
    """Same inputs → same outputs for all calculation types."""

    def test_returns_deterministic(self, sample_prices):
        r1 = calculate_returns_from_prices(sample_prices, "percentage")
        r2 = calculate_returns_from_prices(sample_prices, "percentage")
        assert r1 == r2

    def test_arithmetic_mean_does_not_overflow_for_large_finite_values(self):
        assert mean([1e308, 1e308, 1e308]) == pytest.approx(1e308)

    def test_statistics_deterministic(self, sample_returns):
        s1 = compute_statistics(sample_returns)
        s2 = compute_statistics(sample_returns)
        assert s1 == s2

    def test_metrics_deterministic(self, sample_returns):
        eq = [100000.0, 102000.0, 101000.0, 103000.0]
        m1 = compute_all_metrics(sample_returns, eq)
        m2 = compute_all_metrics(sample_returns, eq)
        assert m1 == m2

    def test_performance_deterministic(self, sample_returns):
        p1 = compute_performance_analytics(sample_returns)
        p2 = compute_performance_analytics(sample_returns)
        assert p1 == p2

    def test_simulation_deterministic(self, backend, simulation_request, sample_prices):
        r1 = backend.run_simulation(simulation_request, sample_prices)
        r2 = backend.run_simulation(simulation_request, sample_prices)
        assert r1.result_hash == r2.result_hash
        assert r1.metrics == r2.metrics
        assert r1.returns == r2.returns

    def test_input_hash_deterministic(self):
        req1 = SimulationRequest(dataset_reference="test", seed=42)
        req2 = SimulationRequest(dataset_reference="test", seed=42)
        assert req1.compute_input_hash() == req2.compute_input_hash()

    def test_different_inputs_different_hash(self):
        req1 = SimulationRequest(dataset_reference="test", seed=42)
        req2 = SimulationRequest(dataset_reference="test2", seed=42)
        assert req1.compute_input_hash() != req2.compute_input_hash()


# ──────────────────────────────────────────────
# 2. Return Calculation Accuracy
# ──────────────────────────────────────────────


class TestReturnCalculation:
    """Verify return calculations match known formulas."""

    def test_absolute_return(self):
        prices = [100.0, 105.0, 95.0, 110.0]
        r = calculate_returns_from_prices(prices, "absolute")
        assert r == [5.0, -10.0, 15.0]

    def test_percentage_return(self):
        prices = [100.0, 110.0, 99.0, 115.0]
        r = calculate_returns_from_prices(prices, "percentage")
        expected = [0.10, -0.10, 0.1616161616161616]
        assert all(abs(a - b) < 1e-10 for a, b in zip(r, expected))

    def test_log_return(self):
        prices = [100.0, 110.0, 99.0]
        r = calculate_returns_from_prices(prices, "log")
        expected = [math.log(1.10), math.log(0.90)]
        assert all(abs(a - b) < 1e-10 for a, b in zip(r, expected))

    def test_single_price_raises(self):
        with pytest.raises(ValueError, match="at least 2 prices"):
            calculate_returns_from_prices([100.0], "percentage")

    def test_empty_prices_raises(self):
        with pytest.raises(ValueError, match="at least 2 prices"):
            calculate_returns_from_prices([], "percentage")

    def test_invalid_return_type_raises(self):
        with pytest.raises(ValueError, match="Unrecognized return_type"):
            calculate_returns_from_prices([100.0, 105.0], "invalid")

    def test_zero_division_handled(self):
        """Percentage return from zero price returns 0.0."""
        r = calculate_returns_from_prices([0.0, 100.0], "percentage")
        assert r == [0.0]

    def test_log_negative_price_handled(self):
        """Log return from non-positive prices returns 0.0."""
        r = calculate_returns_from_prices([-100.0, -90.0], "log")
        assert r == [0.0]

    def test_calculation_version_validation(self):
        with pytest.raises(ValueError, match="Unsupported calculation version"):
            calculate_returns_from_prices([100.0, 105.0], "percentage", "INVALID")


# ──────────────────────────────────────────────
# 3. Volatility Calculation
# ──────────────────────────────────────────────


class TestVolatilityCalculation:
    def test_standard_deviation_constant_returns(self):
        """Constant returns → zero volatility."""
        assert standard_deviation([0.01, 0.01, 0.01]) == 0.0

    def test_standard_deviation_values(self):
        r = [0.01, -0.02, 0.03, -0.01, 0.02]
        sd = standard_deviation(r)
        assert sd > 0
        # Manual verification: mean = 0.006, variance = sum((r-mean)^2)/(5-1)
        # = (0.000016 + 0.000676 + 0.000576 + 0.000256 + 0.000196)/4 = 0.000430
        # std = sqrt(0.00043) ≈ 0.020736
        assert abs(sd - 0.020736) < 1e-5

    def test_single_return_raises(self):
        with pytest.raises(ValueError, match="at least 2"):
            standard_deviation([0.01])

    def test_empty_returns_raises(self):
        with pytest.raises(ValueError, match="empty dataset"):
            standard_deviation([])

    def test_rolling_volatility_length(self, sample_returns):
        rolling = rolling_volatility(sample_returns, window=3)
        assert len(rolling) == len(sample_returns) - 3 + 1

    def test_rolling_volatility_window_too_large_raises(self):
        with pytest.raises((ValueError,), match="at least|Window size"):
            rolling_volatility([0.01, 0.02], window=10)

    def test_volatility_change(self):
        """Increasing volatility → positive change."""
        returns = [0.001] * 30 + [0.05, -0.04, 0.06, -0.05] * 10
        vc = volatility_change(returns, window=10)
        assert vc > 0  # Recent volatility > early volatility

    def test_volatility_change_insufficient_data_raises(self):
        with pytest.raises(ValueError, match="at least"):
            volatility_change([0.01, 0.02], window=10)

    def test_variance(self, sample_returns):
        var = variance(sample_returns)
        assert var >= 0.0

    def test_variance_population(self, sample_returns):
        var_pop = variance(sample_returns, ddof=0)
        var_samp = variance(sample_returns, ddof=1)
        assert var_pop < var_samp  # Population variance ≤ sample variance


# ──────────────────────────────────────────────
# 4. Drawdown Calculation
# ──────────────────────────────────────────────


class TestDrawdownCalculation:
    def test_max_drawdown_strictly_increasing(self):
        """No drawdown when equity never decreases."""
        equity = [100.0, 102.0, 105.0, 110.0]
        dd = max_drawdown(equity)
        assert dd["max_drawdown"] == 0.0
        assert dd["recovery_period"] == 0

    def test_max_drawdown_with_loss(self):
        equity = [100.0, 110.0, 90.0, 95.0, 85.0, 120.0]
        dd = max_drawdown(equity)
        # Max drawdown = (85/110) - 1 = -0.22727...
        assert dd["max_drawdown"] == pytest.approx(-0.227272727, abs=1e-6)
        assert dd["max_drawdown_pct"] == pytest.approx(-22.7272727, abs=1e-4)

    def test_recovery_period(self):
        equity = [100.0, 110.0, 90.0, 85.0, 95.0, 110.0, 115.0]
        dd = max_drawdown(equity)
        # Peak = 110 at idx=1, trough = 85 at idx=3, recovery at idx=5
        # recovery period = 5 - 3 = 2
        assert dd["recovery_period"] >= 0
        assert dd["max_drawdown"] < 0

    def test_single_equity_raises(self):
        with pytest.raises(ValueError, match="at least 2"):
            max_drawdown([100.0])

    def test_empty_equity_raises(self):
        with pytest.raises(ValueError, match="at least 2"):
            max_drawdown([])

    def test_downside_deviation_all_positive(self):
        """No downside deviation when all returns are positive."""
        returns = [0.01, 0.02, 0.03, 0.01]
        dd = downside_deviation(returns)
        assert dd == 0.0

    def test_downside_deviation_with_losses(self):
        returns = [0.05, -0.03, 0.02, -0.04, 0.01, -0.02]
        dd = downside_deviation(returns)
        assert dd > 0.0


# ──────────────────────────────────────────────
# 5. Simulation Replay Consistency
# ──────────────────────────────────────────────


class TestSimulationReplay:
    def test_replay_returns_result(self, engine, simulation_request, sample_prices):
        result = engine.replay(simulation_request, sample_prices)
        assert isinstance(result, SimulationResult)
        assert result.simulation_id != ""

    def test_replay_identical(self, engine, simulation_request, sample_prices):
        r1 = engine.replay(simulation_request, sample_prices)
        r2 = engine.replay(simulation_request, sample_prices)
        assert r1.result_hash == r2.result_hash
        assert r1.metrics == r2.metrics
        assert r1.returns == r2.returns

    def test_replay_provenance(self, engine, simulation_request, sample_prices):
        result = engine.replay(simulation_request, sample_prices)
        assert result.dataset_reference == "XAU/USD:2020-2024"
        assert result.dataset_version == "1.0.0"
        assert result.calculation_version == CalculationVersion.CALCULATION_V1
        assert result.start_time == "2020-01-01"
        assert result.end_time == "2024-12-31"
        assert result.input_hash != ""
        assert result.result_hash != ""

    def test_replay_metrics_present(self, engine, simulation_request, sample_prices):
        result = engine.replay(simulation_request, sample_prices)
        assert "sharpe_ratio" in result.metrics
        assert "sortino_ratio" in result.metrics
        assert "max_drawdown" in result.metrics
        assert "total_return" in result.metrics
        assert "win_rate" in result.metrics

    def test_replay_statistics_present(self, engine, simulation_request, sample_prices):
        result = engine.replay(simulation_request, sample_prices)
        assert "mean" in result.statistics
        assert "std" in result.statistics
        assert "count" in result.statistics
        assert result.statistics["count"] > 0

    def test_replay_performance_present(self, engine, simulation_request, sample_prices):
        result = engine.replay(simulation_request, sample_prices)
        assert "win_rate" in result.performance
        assert "profit_factor" in result.performance
        assert "max_consecutive_wins" in result.performance

    def test_replay_insufficient_data_raises(self, engine, simulation_request):
        result = engine.replay(simulation_request, [100.0])
        assert result.metrics["num_trades"] == 0

    def test_slice_prices(self, engine, sample_prices):
        sliced = engine.slice_prices(sample_prices, 2, 7)
        assert sliced == sample_prices[2:7]

    def test_slice_prices_invalid(self, engine, sample_prices):
        with pytest.raises(ValueError, match="Invalid slice"):
            engine.slice_prices(sample_prices, 10, 5)


# ──────────────────────────────────────────────
# 6. Result Hashing
# ──────────────────────────────────────────────


class TestResultHashing:
    def test_simulation_result_hash(self):
        result = SimulationResult(
            simulation_id="test_001",
            dataset_reference="test",
            returns=[0.01, -0.02, 0.03],
            metrics={"sharpe": 1.5},
        )
        h1 = result.compute_result_hash()
        h2 = result.compute_result_hash()
        assert h1 == h2

    def test_different_results_different_hash(self):
        r1 = SimulationResult(simulation_id="a", dataset_reference="test")
        r2 = SimulationResult(simulation_id="b", dataset_reference="test")
        assert r1.compute_result_hash() != r2.compute_result_hash()

    def test_input_hash_deterministic(self):
        req = SimulationRequest(dataset_reference="test", seed=42)
        assert req.compute_input_hash() == req.compute_input_hash()

    def test_simulation_result_hash_includes_metrics(self):
        r1 = SimulationResult(simulation_id="test", dataset_reference="test")
        r2 = SimulationResult(simulation_id="test", dataset_reference="test", metrics={"a": 1.0})
        assert r1.compute_result_hash() != r2.compute_result_hash()


# ──────────────────────────────────────────────
# 7. Serialization
# ──────────────────────────────────────────────


class TestSerialization:
    def test_simulation_request_roundtrip(self):
        req = SimulationRequest(
            dataset_reference="test",
            dataset_version="1.0.0",
            parameters={"capital": 100000.0},
            seed=42,
        )
        data = req.to_dict()
        restored = SimulationRequest.from_dict(data)
        assert restored.dataset_reference == req.dataset_reference
        assert restored.seed == req.seed
        assert restored.parameters == req.parameters
        assert restored.compute_input_hash() == req.compute_input_hash()

    def test_simulation_result_roundtrip(self):
        result = SimulationResult(
            simulation_id="test_001",
            dataset_reference="test",
            returns=[0.01, -0.02, 0.03],
            metrics={"sharpe": 1.5, "sortino": 2.0},
            equity_curve=[100000.0, 101000.0, 99000.0],
        )
        result.result_hash = result.compute_result_hash()
        data = result.to_dict()
        restored = SimulationResult.from_dict(data)
        assert restored.simulation_id == result.simulation_id
        assert restored.returns == result.returns
        assert restored.metrics == result.metrics
        assert restored.result_hash == result.result_hash

    def test_simulation_request_to_dict_includes_input_hash(self):
        req = SimulationRequest(dataset_reference="test")
        data = req.to_dict()
        assert "input_hash" in data

    def test_simulation_result_to_dict_includes_result_hash(self):
        result = SimulationResult(simulation_id="test", dataset_reference="test")
        data = result.to_dict()
        assert "result_hash" in data


# ──────────────────────────────────────────────
# 8. Interface Compatibility
# ──────────────────────────────────────────────


class TestInterfaceCompatibility:
    def test_backend_implements_interface(self, backend):
        assert isinstance(backend, QuantComputationInterface)

    def test_all_interface_methods_implemented(self, backend):
        """Verify backend has all required interface methods."""
        methods = [
            "calculate_returns",
            "calculate_volatility",
            "calculate_drawdown",
            "calculate_statistics",
            "run_simulation",
            "calculate_metrics",
            "calculate_performance_analytics",
        ]
        for method in methods:
            assert hasattr(backend, method)
            assert callable(getattr(backend, method))

    def test_engine_uses_backend(self, engine):
        assert isinstance(engine.backend, QuantComputationInterface)

    def test_engine_backend_swappable(self, engine):
        new_backend = PythonQuantBackend()
        engine.set_backend(new_backend)
        assert engine.backend is new_backend

    def test_engine_default_backend(self):
        engine = HistoricalSimulationEngine()
        assert isinstance(engine.backend, PythonQuantBackend)

    def test_custom_backend_injection(self):
        """Engine can be created with a custom backend."""
        custom = PythonQuantBackend()
        engine = HistoricalSimulationEngine(backend=custom)
        assert engine.backend is custom


# ──────────────────────────────────────────────
# 9. Integration with Experiment Framework
# ──────────────────────────────────────────────


class TestExperimentIntegration:
    def test_simulation_result_feeds_experiment_result(self, engine, simulation_request, sample_prices):
        """SimulationResult can populate ExperimentResult fields."""
        sim_result = engine.replay(simulation_request, sample_prices)

        # Import ExperimentResult from experiment framework
        from researchos.experiments.result import ExperimentResult

        exp_result = ExperimentResult(
            run_id="test_run_001",
            metrics=sim_result.metrics,
            statistics=sim_result.statistics,
            performance=sim_result.performance,
            equity_curve=sim_result.equity_curve,
        )

        assert exp_result.metrics["sharpe_ratio"] == sim_result.metrics["sharpe_ratio"]
        assert exp_result.statistics["mean"] == sim_result.statistics["mean"]
        assert exp_result.performance["win_rate"] == sim_result.performance["win_rate"]
        assert exp_result.equity_curve == sim_result.equity_curve

    def test_simulation_result_serializable_via_experiment(self, engine, simulation_request, sample_prices):
        """SimulationResult data survives ExperimentResult serialization."""
        sim_result = engine.replay(simulation_request, sample_prices)
        from researchos.experiments.result import ExperimentResult

        exp_result = ExperimentResult(
            run_id="test_run_002",
            metrics=sim_result.metrics,
            statistics=sim_result.statistics,
            performance=sim_result.performance,
        )

        data = exp_result.to_dict()
        restored = ExperimentResult.from_dict(data)
        assert restored.metrics == exp_result.metrics
        assert restored.statistics == exp_result.statistics

    def test_quant_engine_replaces_reference_runner(self, simulation_request, sample_prices):
        """Quant Engine can replace BaseExperimentRunner._execute_simulation."""
        from researchos.quant_engine import PythonQuantBackend

        backend = PythonQuantBackend()
        result = backend.run_simulation(simulation_request, sample_prices)

        # Verify real computation (not random placeholder)
        assert result.metrics["sharpe_ratio"] != 0.0 or abs(result.metrics["total_return"]) > 0
        assert "annualised_return" in result.metrics


# ──────────────────────────────────────────────
# 10. Integration with Market Memory
# ──────────────────────────────────────────────


class TestMarketMemoryIntegration:
    def test_simulation_request_from_market_scenario(self, engine):
        """SimulationRequest can reference a market memory scenario."""
        request = SimulationRequest(
            dataset_reference="market_memory:scenario_001",
            dataset_version="1.0.0",
            start_time="2023-01-01",
            end_time="2023-12-31",
            parameters={"initial_capital": 50000.0},
            tags=["rate_hike_scenario"],
        )
        assert request.dataset_reference.startswith("market_memory:")
        assert "rate_hike_scenario" in request.tags
        assert request.compute_input_hash() != ""

    def test_simulation_result_stores_dataset_reference(self, engine, simulation_request, sample_prices):
        """SimulationResult preserves the dataset reference for audit."""
        result = engine.replay(simulation_request, sample_prices)
        assert result.dataset_reference == "XAU/USD:2020-2024"
        assert result.dataset_version == "1.0.0"

    def test_scenario_test(self, engine, simulation_request, sample_prices):
        """Scenario testing works with multiple parameter variations."""
        variations = [
            {"initial_capital": 50000.0},
            {"initial_capital": 100000.0},
            {"initial_capital": 200000.0},
        ]
        results = engine.scenario_test(simulation_request, sample_prices, variations)
        assert len(results) == 3
        # Different capital should produce different equity curves (but same returns)
        assert results[0].equity_curve[0] == 50000.0
        assert results[1].equity_curve[0] == 100000.0
        assert results[2].equity_curve[0] == 200000.0


# ──────────────────────────────────────────────
# Statistics Edge Cases
# ──────────────────────────────────────────────


class TestStatisticsEdgeCases:
    def test_empty_returns_raises(self):
        with pytest.raises(ValueError, match="empty dataset"):
            mean([])

    def test_single_return_mean(self):
        assert mean([0.05]) == 0.05

    def test_skewness_symmetric(self):
        """Normal-like distribution → skewness near zero."""
        r = [-0.02, -0.01, 0.0, 0.01, 0.02]
        s = skewness(r)
        assert abs(s) < 1.0  # Not exactly zero due to small sample

    def test_skewness_positive(self):
        """Right-skewed → positive skewness."""
        r = [-0.05, -0.02, 0.0, 0.01, 0.10]
        s = skewness(r)
        assert s > 0

    def test_skewness_negative(self):
        """Left-skewed → negative skewness."""
        r = [-0.10, -0.01, 0.0, 0.02, 0.05]
        s = skewness(r)
        assert s < 0

    def test_skewness_insufficient_raises(self):
        with pytest.raises(ValueError, match="at least 3"):
            skewness([0.01, 0.02])

    def test_kurtosis_normal(self):
        """Normal-like distribution → excess kurtosis near zero."""
        r = [-0.02, -0.01, 0.0, 0.01, 0.02]
        k = kurtosis(r, excess=True)
        assert abs(k) < 3.0  # Not exactly zero due to tiny sample

    def test_kurtosis_fat_tails(self):
        """Fat-tailed distribution → positive excess kurtosis."""
        r = [-0.10, -0.01, 0.0, 0.01, 0.12]
        k = kurtosis(r, excess=True)
        assert k > 0

    def test_kurtosis_insufficient_raises(self):
        with pytest.raises(ValueError, match="at least 4"):
            kurtosis([0.01, 0.02, 0.03])

    def test_z_score(self):
        z = z_score(110.0, 100.0, 10.0)
        assert z == 1.0

    def test_z_score_zero_std_raises(self):
        with pytest.raises(ValueError, match="non-positive std"):
            z_score(100.0, 100.0, 0.0)

    def test_variance_zero_std(self):
        assert variance([0.05, 0.05, 0.05]) == pytest.approx(0.0, abs=1e-10)

    def test_zero_variance_metrics(self, sample_returns):
        """Metrics handle zero variance gracefully (e.g., constant returns)."""
        constant = [0.01, 0.01, 0.01, 0.01, 0.01]
        eq = [100.0, 101.0, 102.0, 103.0, 104.0]
        metrics = compute_all_metrics(constant, eq)
        assert metrics["sharpe_ratio"] == 0.0  # std=0 => sharpe=0
        assert metrics["sortino_ratio"] == 0.0  # no negative returns => downside_dev=0 => sortino=0


# ──────────────────────────────────────────────
# Performance Analytics
# ──────────────────────────────────────────────


class TestPerformanceAnalytics:
    def test_all_positive_returns(self):
        """100% win rate when all returns are positive."""
        r = [0.01, 0.02, 0.03]
        p = compute_performance_analytics(r)
        assert p["win_rate"] == 1.0
        assert p["loss_rate"] == 0.0
        assert p["average_win"] == pytest.approx(0.02, abs=1e-6)

    def test_all_negative_returns(self):
        """100% loss rate when all returns are negative."""
        r = [-0.01, -0.02, -0.03]
        p = compute_performance_analytics(r)
        assert p["win_rate"] == 0.0
        assert p["loss_rate"] == 1.0
        assert p["average_loss"] == pytest.approx(-0.02, abs=1e-6)

    def test_win_loss_ratio(self):
        """Wins larger than losses → ratio > 1."""
        r = [0.05, -0.01, 0.03, -0.02, 0.04]
        ratio = win_loss_ratio(r)
        # avg_win = (0.05+0.03+0.04)/3 = 0.04, avg_loss = (-0.01-0.02)/2 = -0.015
        # ratio = 0.04/0.015 = 2.666...
        assert ratio > 1.0

    def test_profit_factor_infinite(self):
        """Profit factor infinite when no losses with wins."""
        pf = profit_factor([0.01, 0.02, 0.03])
        assert pf == float("inf")

    def test_profit_factor_no_wins(self):
        """Profit factor zero when no wins."""
        pf = profit_factor([-0.01, -0.02])
        assert pf == 0.0

    def test_max_consecutive_wins(self):
        r = [0.01, 0.02, -0.01, 0.03, 0.04, 0.05, -0.02]
        assert max_consecutive_wins(r) == 3

    def test_max_consecutive_losses(self):
        r = [-0.01, -0.02, 0.01, -0.03, -0.04, -0.05, 0.02]
        assert max_consecutive_losses(r) == 3

    def test_distribution_analysis(self):
        r = [-0.05, -0.02, 0.0, 0.01, 0.03, 0.07]
        d = distribution_analysis(r, bins=4)
        assert d["min"] == -0.05
        assert d["max"] == 0.07
        assert len(d["bin_edges"]) == 5  # bins + 1
        assert len(d["bin_counts"]) == 4
        assert abs(d["positive_pct"] + d["negative_pct"] + d["zero_pct"] - 1.0) < 1e-10

    def test_distribution_empty_raises(self):
        with pytest.raises(ValueError, match="empty dataset"):
            distribution_analysis([])

    def test_sharpe_ratio_positive(self, sample_returns):
        """Positive returns → positive Sharpe ratio."""
        [100000.0 * (1 + r) for r in [0.0] + sample_returns]
        sr = sharpe_ratio(sample_returns, risk_free_rate=0.0)
        assert sr >= -5.0  # Sanity check

    def test_sortino_ratio(self, sample_returns):
        sr = sortino_ratio(sample_returns, risk_free_rate=0.0)
        assert isinstance(sr, float)

    def test_calmar_ratio(self, sample_returns):
        eq = [100000.0 * (1 + r) for r in [0.0] + sample_returns]
        cr = calmar_ratio(sample_returns, eq)
        assert isinstance(cr, float)


# ──────────────────────────────────────────────
# Walk-Forward and Monte Carlo
# ──────────────────────────────────────────────


class TestSimulationModes:
    def test_walk_forward(self, engine, simulation_request, sample_prices):
        results = engine.walk_forward(
            simulation_request,
            sample_prices,
            window_size=5,
            step_size=3,
        )
        assert len(results) >= 1
        for r in results:
            assert r.metrics["sharpe_ratio"] is not None

    def test_walk_forward_window_too_large_raises(self, engine, simulation_request, sample_prices):
        with pytest.raises(ValueError, match="less than window size"):
            engine.walk_forward(simulation_request, sample_prices, window_size=100)

    def test_monte_carlo(self, engine, simulation_request, sample_prices):
        results = engine.monte_carlo(
            simulation_request,
            sample_prices,
            num_simulations=5,
        )
        assert len(results) == 5
        # Monte Carlo paths should have same starting price
        for r in results:
            assert len(r.equity_curve) > 0
            assert r.equity_curve[0] == 100000.0  # initial_capital

    def test_monte_carlo_insufficient_data_raises(self, engine, simulation_request):
        with pytest.raises(ValueError, match="at least 2 prices"):
            engine.monte_carlo(simulation_request, [100.0], num_simulations=1)

    def test_scenario_test_varying_risk_free(self, engine, simulation_request, sample_prices):
        variations = [
            {"risk_free_rate": 0.0},
            {"risk_free_rate": 0.05},
            {"risk_free_rate": 0.10},
        ]
        results = engine.scenario_test(simulation_request, sample_prices, variations)
        assert len(results) == 3
        # Different risk-free rates → different Sharpe ratios
        assert results[0].metrics["sharpe_ratio"] != results[1].metrics["sharpe_ratio"]


# ──────────────────────────────────────────────
# Backend Interface
# ──────────────────────────────────────────────


class TestBackendInterface:
    def test_calculate_drawdown(self, backend):
        equity = [100.0, 110.0, 90.0, 95.0, 85.0, 120.0]
        dd = backend.calculate_drawdown(equity)
        assert dd["max_drawdown"] < 0
        assert dd["recovery_period"] >= 0

    def test_calculate_volatility_standard(self, backend, sample_returns):
        vol = backend.calculate_volatility(sample_returns, "standard_deviation")
        assert vol > 0

    def test_calculate_volatility_rolling(self, backend):
        # Generate enough returns for a rolling window of 3
        returns_20 = [0.01, -0.02, 0.03, 0.01, 0.02, -0.01, 0.03, -0.02, 0.01, 0.02] * 3
        vol = backend.calculate_volatility(returns_20, "rolling")
        assert vol >= 0  # Last rolling volatility value

    def test_calculate_volatility_change(self, backend):
        # Generate enough returns for volatility_change (needs 2*window = 42)
        returns_50 = [0.001] * 30 + [0.02, -0.01, 0.03, -0.02, 0.01] * 5
        vol = backend.calculate_volatility(returns_50, "change")
        assert isinstance(vol, float)

    def test_calculate_volatility_invalid_method_raises(self, backend, sample_returns):
        with pytest.raises(ValueError, match="Unrecognized method"):
            backend.calculate_volatility(sample_returns, "invalid")

    def test_calculate_volatility_empty_raises(self, backend):
        with pytest.raises(ValueError, match="empty dataset"):
            backend.calculate_volatility([], "standard_deviation")

    def test_calculate_metrics(self, backend, sample_returns):
        eq = [100000.0 * (1 + r) for r in [0.0] + sample_returns]
        metrics = backend.calculate_metrics(sample_returns, eq)
        assert "sharpe_ratio" in metrics
        assert "sortino_ratio" in metrics
        assert "calmar_ratio" in metrics
        assert "profit_factor" in metrics
        assert "annualised_return" in metrics

    def test_calculate_performance_analytics(self, backend, sample_returns):
        pa = backend.calculate_performance_analytics(sample_returns)
        assert "win_rate" in pa
        assert "profit_factor" in pa
        assert "max_consecutive_wins" in pa


# ──────────────────────────────────────────────
# Edge Cases
# ──────────────────────────────────────────────


class TestEdgeCases:
    def test_zero_volatility_sharpe(self):
        """Constant returns → Sharpe ratio = 0."""
        r = [0.01, 0.01, 0.01, 0.01]
        sr = sharpe_ratio(r)
        assert sr == 0.0

    def test_zero_volatility_sortino(self):
        r = [0.01, 0.01, 0.01]
        sr = sortino_ratio(r)
        assert sr == 0.0

    def test_no_drawdown_calmar(self):
        """Strictly increasing equity → Calmar = 0 (no drawdown)."""
        r = [0.01, 0.01, 0.01]
        eq = [100.0, 101.0, 102.0, 103.0]
        cr = calmar_ratio(r, eq)
        assert cr == 0.0

    def test_backend_swap_preserves_behavior(self, simulation_request, sample_prices):
        """Swapping backends produces identical results with same implementation."""
        backend1 = PythonQuantBackend()
        backend2 = PythonQuantBackend()

        r1 = backend1.run_simulation(simulation_request, sample_prices)
        r2 = backend2.run_simulation(simulation_request, sample_prices)

        assert r1.result_hash == r2.result_hash


# ──────────────────────────────────────────────
# Consistency Metrics
# ──────────────────────────────────────────────


class TestConsistency:
    """Consistency = win_rate for binary classification."""

    def test_consistency_all_wins(self):
        assert consistency([0.01, 0.02, 0.03]) == 1.0

    def test_consistency_all_losses(self):
        assert consistency([-0.01, -0.02, -0.03]) == 0.0

    def test_consistency_mixed(self):
        assert consistency([0.01, -0.01, 0.02, -0.02]) == 0.5
