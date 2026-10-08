"""
Historical Simulation Engine for the Quant Computation Engine.

Provides:
    - Historical replay: Re-run a simulation over a specific time window
    - Configurable time windows: Slice price data by start/end time
    - Scenario testing: Run simulations with varying parameters
    - Walk-forward: Sequential simulation over rolling windows

Every simulation stores:
    - Dataset reference
    - Parameters
    - Start/end time
    - Calculation version
    - Result hash

This is a COMPUTATION LAYER — NOT a trading engine or execution system.

Based on Article XVII: Object Model — Quant Engine Layer.
"""

from __future__ import annotations

import random
from typing import Any

from researchos.quant_engine.backend import PythonQuantBackend
from researchos.quant_engine.interface import QuantComputationInterface
from researchos.quant_engine.models import (
    SimulationRequest,
    SimulationResult,
)


class HistoricalSimulationEngine:
    """
    Engine for executing historical simulations.

    Supports:
        - Historical replay over a price series
        - Configurable time windows
        - Scenario testing with parameter variations
        - Walk-forward analysis

    The engine delegates actual computation to a QuantComputationInterface
    implementation (Python or future C++).
    """

    def __init__(
        self,
        backend: QuantComputationInterface | None = None,
    ):
        """
        Initialize the simulation engine.

        Args:
            backend: Computation backend. Uses PythonQuantBackend if not provided.
        """
        self._backend = backend or PythonQuantBackend()
        self._rng = random.Random()

    @property
    def backend(self) -> QuantComputationInterface:
        """Get the current computation backend."""
        return self._backend

    def set_backend(self, backend: QuantComputationInterface) -> None:
        """
        Swap the computation backend.

        This is the key integration point for future C++ Quant Engine:
            engine.set_backend(CppQuantBackend())

        Args:
            backend: New backend implementing QuantComputationInterface.
        """
        self._backend = backend

    def replay(
        self,
        request: SimulationRequest,
        prices: list[float],
    ) -> SimulationResult:
        """
        Execute a historical replay simulation.

        Re-runs the simulation over the exact price series provided.
        The same request + prices always produces the same result.

        Args:
            request: Complete simulation request with parameters.
            prices: Ordered list of prices (oldest to newest).

        Returns:
            SimulationResult with all computed metrics and provenance.
        """
        return self._backend.run_simulation(
            request=request,
            dataset=prices,
            calculation_version=request.calculation_version,
        )

    def slice_prices(
        self,
        prices: list[float],
        start_idx: int = 0,
        end_idx: int | None = None,
    ) -> list[float]:
        """
        Slice a price series to a specific time window.

        Args:
            prices: Full price series.
            start_idx: Starting index (inclusive).
            end_idx: Ending index (exclusive). If None, uses all remaining prices.

        Returns:
            Sliced price series.

        Raises:
            ValueError: If indices are out of bounds.
        """
        if end_idx is None:
            end_idx = len(prices)

        if start_idx < 0 or end_idx > len(prices) or start_idx >= end_idx:
            raise ValueError(f"Invalid slice indices: start={start_idx}, end={end_idx}, length={len(prices)}")

        return prices[start_idx:end_idx]

    def scenario_test(
        self,
        base_request: SimulationRequest,
        prices: list[float],
        parameter_variations: list[dict[str, Any]],
    ) -> list[SimulationResult]:
        """
        Run scenario testing with parameter variations.

        Each variation is a dict of parameter overrides applied to the
        base request. This allows testing how different parameters affect
        the simulation outcome.

        Args:
            base_request: Base simulation request.
            prices: Price series for the simulation.
            parameter_variations: List of parameter override dicts.

        Returns:
            List of SimulationResult (one per variation).
        """
        results: list[SimulationResult] = []

        for i, overrides in enumerate(parameter_variations):
            # Deep copy of request parameters with overrides
            merged_params = dict(base_request.parameters)
            merged_params.update(overrides)

            variant_request = SimulationRequest(
                dataset_reference=base_request.dataset_reference,
                dataset_version=base_request.dataset_version,
                calculation_version=base_request.calculation_version,
                start_time=base_request.start_time,
                end_time=base_request.end_time,
                parameters=merged_params,
                seed=base_request.seed + i,
                tags=base_request.tags + [f"scenario_{i}"],
            )

            result = self.replay(variant_request, prices)
            results.append(result)

        return results

    def walk_forward(
        self,
        request: SimulationRequest,
        prices: list[float],
        window_size: int = 252,
        step_size: int = 63,
    ) -> list[SimulationResult]:
        """
        Execute a walk-forward analysis.

        Divides the price series into rolling windows and runs a separate
        simulation for each window. This tests how the strategy performs
        across different market regimes.

        Args:
            request: Base simulation request.
            prices: Full price series.
            window_size: Size of each window in periods.
            step_size: Step size between windows in periods.

        Returns:
            List of SimulationResult (one per window).
        """
        if len(prices) < window_size:
            raise ValueError(f"Price series length ({len(prices)}) is less than window size ({window_size})")

        results: list[SimulationResult] = []
        num_windows = ((len(prices) - window_size) // step_size) + 1

        for i in range(num_windows):
            start_idx = i * step_size
            end_idx = start_idx + window_size

            window_prices = prices[start_idx:end_idx]

            window_request = SimulationRequest(
                dataset_reference=request.dataset_reference,
                dataset_version=request.dataset_version,
                calculation_version=request.calculation_version,
                start_time=f"window_{i}_start",
                end_time=f"window_{i}_end",
                parameters=dict(request.parameters),
                seed=request.seed + i,
                tags=request.tags + [f"window_{i}"],
            )

            result = self.replay(window_request, window_prices)
            results.append(result)

        return results

    def monte_carlo(
        self,
        request: SimulationRequest,
        prices: list[float],
        num_simulations: int = 100,
    ) -> list[SimulationResult]:
        """
        Execute Monte Carlo simulations.

        Generates synthetic price paths by resampling from historical returns
        and runs a simulation for each path. This tests the robustness of
        the strategy under different market conditions.

        Args:
            request: Base simulation request.
            prices: Historical price series for parameterising the resampling.
            num_simulations: Number of simulated price paths.

        Returns:
            List of SimulationResult (one per simulation).
        """
        if len(prices) < 2:
            raise ValueError(f"Need at least 2 prices for Monte Carlo, got {len(prices)}")

        # Calculate historical returns for resampling
        from researchos.quant_engine.statistics import calculate_returns_from_prices

        historical_returns = calculate_returns_from_prices(prices, "percentage")

        if not historical_returns:
            raise ValueError("No returns available for Monte Carlo simulation")

        results: list[SimulationResult] = []

        for i in range(num_simulations):
            self._rng = random.Random(request.seed + i)

            # Generate synthetic price path by resampling
            synthetic_prices = [prices[0]]
            for _ in range(len(historical_returns)):
                sampled_return = self._rng.choice(historical_returns)
                synthetic_prices.append(synthetic_prices[-1] * (1.0 + sampled_return))

            mc_request = SimulationRequest(
                dataset_reference=request.dataset_reference,
                dataset_version=request.dataset_version,
                calculation_version=request.calculation_version,
                start_time=request.start_time,
                end_time=request.end_time,
                parameters=dict(request.parameters),
                seed=request.seed + i,
                tags=request.tags + [f"monte_carlo_{i}"],
            )

            result = self.replay(mc_request, synthetic_prices)
            results.append(result)

        return results
