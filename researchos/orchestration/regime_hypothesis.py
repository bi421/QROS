"""Opt-in, offline statistical tests for regime directional value.

This module is never called by the incremental candle-update path. It uses a
chronological holdout and a moving-block bootstrap to account partially for
serial dependence in forward returns. It is a research diagnostic, not proof
of profitable trading or calibrated state probabilities.
"""

from __future__ import annotations

import math

import numpy as np

STATE_SIGN = {"UP": 1.0, "DOWN": -1.0, "RANGE": 0.0}


def evaluate_regime_directional_value(
    states: list[str | None] | tuple[str | None, ...],
    closes: list[float] | np.ndarray,
    *,
    horizon: int = 5,
    holdout_fraction: float = 0.30,
    block_length: int | None = None,
    bootstrap_replicates: int = 999,
    seed: int = 20261016,
    max_observations: int = 50_000,
) -> dict[str, object]:
    """Test H0: holdout mean signed forward log return is zero.

    Each state at t is paired with close[t+horizon]/close[t]. Only the final
    chronological holdout is tested. A bounded tail cap limits CPU and memory.
    """
    prices = np.asarray(closes, dtype=np.float64)
    if prices.ndim != 1 or len(prices) != len(states):
        raise ValueError("states and closes must be one-dimensional and equal length")
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("closes must be finite and positive")
    if horizon < 1 or not (0.1 <= holdout_fraction <= 0.5):
        raise ValueError("horizon must be >= 1 and holdout_fraction in [0.1, 0.5]")
    if bootstrap_replicates < 199 or max_observations < 100:
        raise ValueError("bootstrap_replicates must be >= 199 and max_observations >= 100")
    if block_length is None:
        block_length = max(horizon, int(round(len(prices) ** (1 / 3))))
    if block_length < horizon or block_length > max_observations:
        raise ValueError("block_length must be >= horizon and <= max_observations")

    split = int(len(prices) * (1.0 - holdout_fraction))
    stop = len(prices) - horizon
    if split >= stop:
        raise ValueError("insufficient holdout observations for the selected horizon")

    indexes = np.arange(split, stop, dtype=np.int64)
    if len(indexes) > max_observations:
        indexes = indexes[-max_observations:]
    valid = np.fromiter(
        (states[i] in STATE_SIGN for i in indexes),
        dtype=bool,
        count=len(indexes),
    )
    indexes = indexes[valid]
    if len(indexes) < max(100, block_length * 5):
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "reason": "too few valid chronological holdout observations",
            "null_hypothesis": "mean signed forward log return equals zero",
            "execution_enabled": False,
        }

    signs = np.fromiter((STATE_SIGN[states[i]] for i in indexes), dtype=np.float64)
    forward_returns = np.log(prices[indexes + horizon] / prices[indexes])
    signed_returns = signs * forward_returns
    observed_mean = float(np.mean(signed_returns))
    centered = signed_returns - observed_mean

    # Moving-block bootstrap: sample contiguous blocks from centered outcomes.
    rng = np.random.default_rng(seed)
    n = len(centered)
    starts = np.arange(max(1, n - block_length + 1), dtype=np.int64)
    blocks_needed = math.ceil(n / block_length)
    null_means = np.empty(bootstrap_replicates, dtype=np.float64)
    centered_blocks = np.lib.stride_tricks.sliding_window_view(centered, block_length)
    for replicate in range(bootstrap_replicates):
        selected = rng.choice(starts, size=blocks_needed, replace=True)
        sample = centered_blocks[selected].reshape(-1)[:n]
        null_means[replicate] = float(np.mean(sample))

    p_value = float(
        (1 + np.count_nonzero(np.abs(null_means) >= abs(observed_mean)))
        / (bootstrap_replicates + 1)
    )
    # Bootstrap confidence interval for the mean under the empirical process.
    boot_means = np.empty(bootstrap_replicates, dtype=np.float64)
    for replicate in range(bootstrap_replicates):
        selected = rng.choice(starts, size=blocks_needed, replace=True)
        sample = centered_blocks[selected].reshape(-1)[:n] + observed_mean
        boot_means[replicate] = float(np.mean(sample))
    ci_low, ci_high = np.quantile(boot_means, [0.025, 0.975]).tolist()

    up_count = sum(states[i] == "UP" for i in indexes)
    down_count = sum(states[i] == "DOWN" for i in indexes)
    range_count = sum(states[i] == "RANGE" for i in indexes)
    return {
        "status": "COMPLETED",
        "test_name": "moving_block_bootstrap_mean_signed_forward_log_return",
        "null_hypothesis": "H0: mean signed forward log return equals zero",
        "alternative_hypothesis": "H1: mean signed forward log return differs from zero",
        "horizon_bars": horizon,
        "holdout_fraction": holdout_fraction,
        "holdout_start_index": int(indexes[0]),
        "holdout_end_index_exclusive": int(indexes[-1] + horizon + 1),
        "observation_count": int(n),
        "state_counts": {"UP": int(up_count), "DOWN": int(down_count), "RANGE": int(range_count)},
        "block_length": int(block_length),
        "bootstrap_replicates": int(bootstrap_replicates),
        "seed": int(seed),
        "mean_signed_forward_log_return": observed_mean,
        "ci_95_percent": [float(ci_low), float(ci_high)],
        "p_value_two_sided": p_value,
        "alpha_0_05_reject_null": bool(p_value < 0.05),
        "multiple_testing_correction": "NOT_APPLIED; pre-register one horizon before interpretation",
        "limitations": [
            "A rejection does not prove net profitability or causal predictability.",
            "Forward outcomes overlap when horizon > 1; block bootstrap only partially addresses dependence.",
            "No spread, commission, slippage, or latency costs are included.",
            "The state classifier and thresholds are heuristic and must be frozen before final holdout use.",
            "This diagnostic is opt-in and is not run by the incremental engine.",
        ],
        "execution_enabled": False,
    }


__all__ = ["evaluate_regime_directional_value"]
