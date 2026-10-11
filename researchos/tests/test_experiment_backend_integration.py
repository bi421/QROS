"""
Integration tests: Experiment Framework ↔ Quant Computation Backend.

Verifies the architectural boundary introduced by the Experiment/Quant-Backend
refactor:

    Data Engine
        ↓
    Dataset / Historical Data Contract
        ↓
    QuantComputationInterface
        ↓
    PythonQuantBackend
        ↓
    ExperimentRunner
        ↓
    ExperimentResult

The Experiment Framework must NEVER:
    - load CSV files directly
    - parse OHLCV data
    - know MT5/TradingView formats
    - contain financial calculation logic

These tests assert:
    1. Same dataset + same config → identical result (determinism).
    2. Different dataset → different result.
    3. No RNG dependency remains in the experiment execution path.
    4. ExperimentResult stores full computation provenance.
    5. The runner forwards the raw dataset contract to the backend
       (the backend owns all dataset-contract normalization).
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

from researchos.experiments.contracts import DatasetConfig, SimulationConfig
from researchos.experiments.experiment import Experiment
from researchos.experiments.result import ExperimentResult
from researchos.experiments.runner import BaseExperimentRunner
from researchos.quant_engine.backend import PythonQuantBackend
from researchos.quant_engine.interface import QuantComputationInterface
from researchos.quant_engine.models import (
    CalculationVersion,
    SimulationRequest,
    SimulationResult,
)

# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


def _prices(n: int = 252, base: float = 100.0, drift: float = 0.0001) -> list[float]:
    """Deterministic synthetic price series."""
    return [base * (1.0 + drift * i) for i in range(n)]


def _make_dataset_contract() -> list[dict[str, Any]]:
    """A list-of-dicts OHLCV-style dataset contract (backend must normalize)."""
    out: list[dict[str, Any]] = []
    ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
    price = 100.0
    for i in range(252):
        out.append(
            {
                "timestamp": ts,
                "open": price,
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price,
                "volume": 1000 + i,
            }
        )
        price *= 1.0001
        ts = ts.replace(day=ts.day + 1) if ts.day < 28 else ts.replace(month=ts.month + 1, day=1)
    return out


def _make_experiment(name: str = "Integration Test") -> Experiment:
    exp = Experiment(
        hypothesis_id="hyp_integration",
        name=name,
        dataset_config=DatasetConfig(source="integration_source"),
        simulation_config=SimulationConfig(seed=42, initial_capital=100_000.0),
    )
    exp.mark_ready()
    return exp


def _metrics_key(result: ExperimentResult) -> str:
    """Deterministic key derived from a result's metrics + provenance."""
    return result.result_hash


# ──────────────────────────────────────────────
# 1. Same dataset + same config = identical result
# ──────────────────────────────────────────────


class TestDeterminism:
    def test_same_dataset_same_config_identical_result(self):
        """Running the same experiment twice over the same dataset is identical."""
        runner = BaseExperimentRunner()
        exp = _make_experiment()

        run1, result1 = runner.run(exp, _prices())
        run2, result2 = runner.run(exp, _prices())

        assert run1.status.value == "Completed"
        assert run2.status.value == "Completed"
        assert result1.result_hash == result2.result_hash
        assert result1.metrics == result2.metrics
        assert result1.statistics == result2.statistics

    def test_same_dataset_historical_contract_identical(self):
        """Same HistoricalDataset-like contract normalizes to the same result."""
        runner = BaseExperimentRunner()
        exp = _make_experiment()

        ds1 = _make_dataset_contract()
        ds2 = _make_dataset_contract()

        _, result1 = runner.run(exp, ds1)
        _, result2 = runner.run(exp, ds2)

        assert result1.result_hash == result2.result_hash

    def test_backend_determinism_direct(self):
        """Backend level: same request + same dataset → identical SimulationResult."""
        backend = PythonQuantBackend()
        request = SimulationRequest(
            dataset_reference="direct",
            parameters={"initial_capital": 100000.0},
            seed=42,
        )
        prices = _prices()
        r1: SimulationResult = backend.run_simulation(request, prices)
        r2: SimulationResult = backend.run_simulation(request, prices)

        assert r1.result_hash == r2.result_hash
        assert r1.metrics == r2.metrics


# ──────────────────────────────────────────────
# 2. Different dataset → different result
# ──────────────────────────────────────────────


class TestDifferentDataset:
    def test_different_prices_produce_different_result(self):
        """A different price series must change the computed result hash."""
        runner = BaseExperimentRunner()
        exp = _make_experiment()

        _, result_up = runner.run(exp, _prices(drift=0.001))  # trending up
        _, result_down = runner.run(exp, _prices(drift=-0.001))  # trending down

        assert result_up.result_hash != result_down.result_hash
        assert result_up.metrics != result_down.metrics

    def test_different_dataset_reference_changes_input_hash(self):
        """Different dataset reference changes provenance input_hash."""
        backend = PythonQuantBackend()
        prices = _prices()

        req_a = SimulationRequest(dataset_reference="XAU/USD", seed=42)
        req_b = SimulationRequest(dataset_reference="EUR/USD", seed=42)

        res_a = backend.run_simulation(req_a, prices)
        res_b = backend.run_simulation(req_b, prices)

        assert res_a.input_hash != res_b.input_hash


# ──────────────────────────────────────────────
# 3. No RNG dependency remains
# ──────────────────────────────────────────────


class TestNoRngDependency:
    def test_experiment_execution_is_rng_free(self, monkeypatch):
        """Running an experiment must never touch the random module."""

        def _raise(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("random module accessed during experiment execution")

        monkeypatch.setattr(random, "random", _raise)
        monkeypatch.setattr(random, "uniform", _raise)
        monkeypatch.setattr(random, "randint", _raise)
        monkeypatch.setattr(random, "choice", _raise)
        monkeypatch.setattr(random, "gauss", _raise)
        monkeypatch.setattr(random, "Random", _raise)

        runner = BaseExperimentRunner()
        exp = _make_experiment()
        run, result = runner.run(exp, _prices())

        assert run.status.value == "Completed"
        assert len(result.metrics) > 0

    def test_backend_has_no_rng_state(self):
        """The PythonQuantBackend must be stateless w.r.t. randomness."""
        backend = PythonQuantBackend()
        # No hidden RNG state on the instance.
        assert not any("rng" in attr.lower() for attr in vars(backend))


# ──────────────────────────────────────────────
# 4. ExperimentResult stores computation provenance
# ──────────────────────────────────────────────


class TestProvenance:
    def test_result_stores_computation_provenance(self):
        """ExperimentResult must carry computation provenance statistics."""
        runner = BaseExperimentRunner()
        exp = _make_experiment()
        _, result = runner.run(exp, _prices())

        assert result.statistics["computation_backend"] == "PythonQuantBackend"
        assert result.statistics["calculation_version"] == "CALCULATION_V1"
        assert result.statistics["input_hash"]
        assert result.statistics["result_hash"]
        assert result.statistics["simulation_id"].startswith("sim_")
        assert result.statistics["dataset_reference"] == "integration_source"

        # Issue #5: dataset_version is now a real content hash, not "1.0.0".
        assert result.statistics["dataset_version"] != "1.0.0"
        assert len(result.statistics["dataset_version"]) == 64  # sha256 hex
        assert result.statistics["seed"] == 42
        assert result.statistics["run_number"] == 1

        # Equity curve and returns preserved as metadata.
        assert "equity_curve" in result.metadata
        assert "returns" in result.metadata
        assert len(result.metadata["equity_curve"]) > 0
        assert len(result.metadata["returns"]) > 0

    def test_run_links_to_result_hash(self):
        """ExperimentRun must link its result hash for integrity."""
        runner = BaseExperimentRunner()
        exp = _make_experiment()
        run, result = runner.run(exp, _prices())

        assert run.result_id == result.id
        assert run.result_hash == result.result_hash


# ──────────────────────────────────────────────
# 5. Runner forwards the raw dataset contract
# ──────────────────────────────────────────────


class TestBoundary:
    def test_runner_forwards_dataset_contract(self):
        """The runner must pass the dataset contract through to the backend
        without parsing OHLCV itself."""
        captured: dict[str, Any] = {}

        class RecordingBackend(PythonQuantBackend):
            def run_simulation(
                self,
                request: SimulationRequest,
                dataset: Any,
                calculation_version: CalculationVersion = CalculationVersion.CALCULATION_V1,
            ) -> SimulationResult:
                captured["dataset"] = dataset
                return super().run_simulation(request, dataset, calculation_version)

        runner = BaseExperimentRunner(backend=RecordingBackend())
        exp = _make_experiment()
        contract = _make_dataset_contract()

        runner.run(exp, contract)

        # The backend receives the exact contract object — no pre-parsing.
        assert captured["dataset"] is contract

    def test_runner_has_no_dataset_parsing_methods(self):
        """The runner must not expose price-extraction / OHLCV-parsing helpers."""
        runner = BaseExperimentRunner()
        # Historical: _extract_prices was owned by the Experiment Framework and
        # has been removed. The runner only forwards the contract.
        assert not hasattr(runner, "_extract_prices")

    def test_backend_accepts_list_of_floats(self):
        """A plain list[float] dataset contract is still accepted."""
        runner = BaseExperimentRunner()
        exp = _make_experiment()
        run, result = runner.run(exp, [100.0, 102.0, 101.0, 104.0, 103.0, 106.0])
        assert run.status.value == "Completed"
        assert len(result.metrics) > 0

    def test_interface_uses_dataset_param(self):
        """QuantComputationInterface.run_simulation must use `dataset` param."""
        import inspect

        sig = inspect.signature(QuantComputationInterface.run_simulation)
        params = list(sig.parameters.keys())
        assert params == ["self", "request", "dataset", "calculation_version"]

    def test_insufficient_dataset_raises(self):
        """Backend must reject an insufficient dataset instead of emitting a result."""
        backend = PythonQuantBackend()
        request = SimulationRequest(dataset_reference="x", seed=42)
        with pytest.raises(ValueError, match="at least 2 prices"):
            backend.run_simulation(request, [100.0])


# ──────────────────────────────────────────────
# 6. Backtest artifacts propagate to ExperimentResult
# ──────────────────────────────────────────────


class TestBacktestArtifacts:
    """Mode B backtest artifacts must flow from SimulationResult into ExperimentResult."""

    def _backtest_experiment(self, name: str = "Backtest Artifacts") -> Experiment:
        exp = Experiment(
            hypothesis_id="hyp_backtest",
            name=name,
            dataset_config=DatasetConfig(source="backtest_source"),
            simulation_config=SimulationConfig(
                seed=42,
                initial_capital=100_000.0,
                commission="fixed:10.0",
                slippage="fixed:0.01",
                parameters={"mode": "backtest", "position_size": 100.0},
            ),
        )
        exp.mark_ready()
        return exp

    def test_result_receives_backtest_artifacts(self):
        """ExperimentResult must carry trades/signals/positions/execution_stats."""
        runner = BaseExperimentRunner()
        exp = self._backtest_experiment()
        prices = [100.0, 102.0, 104.0, 103.0, 105.0, 107.0, 106.0, 108.0, 110.0, 112.0]

        run, result = runner.run(exp, prices)

        assert run.status.value == "Completed"
        # Buy & hold over 10 bars produces exactly 1 round-trip trade.
        assert len(result.trades) == 1
        # Entry + end-of-data liquidation signals.
        assert len(result.signals) == 2
        # One position snapshot per bar.
        assert len(result.metadata["positions"]) == len(prices)
        # Execution stats carry deterministic fill data (entry + liquidation).
        assert result.metadata["execution_stats"]["num_fills"] == 2
        assert result.metadata["execution_stats"]["num_trades"] == 1
        assert result.metadata["execution_stats"]["strategy"] == "buy_and_hold"

    def test_backtest_artifacts_deterministic(self):
        """Identical backtest config + dataset → identical artifacts & result_hash."""
        runner = BaseExperimentRunner()
        exp = self._backtest_experiment()
        prices = [100.0, 102.0, 104.0, 103.0, 105.0, 107.0, 106.0, 108.0, 110.0, 112.0]

        run1, result1 = runner.run(exp, prices)
        run2, result2 = runner.run(exp, prices)

        assert result1.result_hash == result2.result_hash
        assert result1.metrics == result2.metrics
        assert result1.trades == result2.trades
        assert result1.signals == result2.signals
        assert result1.metadata["positions"] == result2.metadata["positions"]
        assert result1.metadata["execution_stats"] == result2.metadata["execution_stats"]
