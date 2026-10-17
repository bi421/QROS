"""Candle Momentum & Kinetic Energy feature framework for research.

The term kinetic energy is an analogy: OHLC candles do not reveal physical market
energy, order flow, or liquidity directly. `range_energy_proxy` is a scale-sensitive
proxy (0.5 * range_velocity**2), not physical energy or a calibrated market quantity.
All features are computed from completed bars and rolling statistics exclude the
current bar. This module emits measurements only, never orders.
"""

from __future__ import annotations

from typing import Any, Iterable

from researchos.orchestration.candle_velocity import CandleVelocityEngine


class CandleKineticEngine:
    """Causal candle shape, range-velocity, and acceleration-proxy features."""

    def __init__(self, window: int = 20, z_threshold: float = 2.0) -> None:
        self.window = window
        self.z_threshold = z_threshold
        self._velocity = CandleVelocityEngine(window=window, z_threshold=z_threshold)
        self._previous_velocity: float | None = None

    def reset(self) -> None:
        self._velocity = CandleVelocityEngine(window=self.window, z_threshold=self.z_threshold)
        self._previous_velocity = None

    def update(
        self,
        open_: float,
        high: float,
        low: float,
        close: float,
        *,
        interval_seconds: float = 900.0,
    ) -> dict[str, Any]:
        features = self._velocity.update(open_, high, low, close, interval_seconds=interval_seconds)
        velocity = float(features["range_velocity"])
        previous = self._previous_velocity
        features["range_acceleration_proxy"] = (
            (velocity - previous) / interval_seconds if previous is not None else None
        )
        features["range_energy_proxy"] = 0.5 * velocity * velocity
        features["body_ratio"] = float(features["body_ratio"])
        features["upper_ratio"] = float(features["upper_wick_ratio"])
        features["lower_ratio"] = float(features["lower_wick_ratio"])
        self._previous_velocity = velocity
        return features

    def compute_features(
        self,
        rows: Iterable[tuple[Any, float, float, float, float]],
        *,
        interval_seconds: float = 900.0,
    ) -> list[dict[str, Any]]:
        """Compute feature dicts for (timestamp, open, high, low, close) rows.

        On a timestamp gap, rolling state is reset to prevent cross-gap leakage.
        Polars/DuckDB users can convert these rows/features to their preferred frame;
        the core engine deliberately has no mandatory dataframe dependency.
        """
        output: list[dict[str, Any]] = []
        previous_timestamp = None
        for timestamp, open_, high, low, close in rows:
            if previous_timestamp is not None:
                delta = timestamp - previous_timestamp
                if delta.total_seconds() != interval_seconds:
                    self.reset()
            item = self.update(open_, high, low, close, interval_seconds=interval_seconds)
            item["timestamp"] = (
                timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp)
            )
            output.append(item)
            previous_timestamp = timestamp
        return output


__all__ = ["CandleKineticEngine"]
