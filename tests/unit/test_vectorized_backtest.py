from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from researchos.orchestration.vectorized_backtest import (
    EngineConfig,
    _apply_barrier_step,
    _bootstrap_daily_blocks,
    _bh,
    load_news_mask,
    load_ohlcv_csv,
    run_grid,
)


def synthetic_data(n: int = 600) -> dict[str, Any]:
    rng = np.random.default_rng(123)
    close = 1900 + np.cumsum(rng.normal(0, 0.8, n))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(0.05, 0.7, n)
    low = np.minimum(open_, close) - rng.uniform(0.05, 0.7, n)
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "tick_volume": np.ones(n),
        "real_volume": np.ones(n),
        "timestamp": np.datetime64("2025-01-01T00:00") + np.arange(n) * np.timedelta64(15, "m"),
    }


def test_bh_fdr_cutoff_and_empty_values() -> None:
    passed, cutoff = _bh(np.array([0.001, 0.02, 0.8, 0.03]), 0.05)
    assert passed.tolist() == [True, True, False, True]
    assert cutoff == pytest.approx(0.03)
    passed, cutoff = _bh(np.array([np.nan, np.nan]), 0.05)
    assert not passed.any() and cutoff is None


def test_csv_loader_accepts_utf16_mt5_file(tmp_path: Path) -> None:
    p = tmp_path / "bars.csv"
    p.write_text(
        "2025.01.01 00:00,100,101,99,100.5,10,20\n2025.01.01 00:15,100.5,102,100,101.5,11,21\n",
        encoding="utf-16",
    )
    data = load_ohlcv_csv(p)
    assert len(data["close"]) == 2
    assert data["close"][1] == pytest.approx(101.5)


def test_news_mask_blocks_both_sides_of_event(tmp_path: Path) -> None:
    p = tmp_path / "news.csv"
    p.write_text("timestamp,title\n2025-01-01 01:00,rate decision\n", encoding="utf-8")
    ts = np.datetime64("2025-01-01T00:00") + np.arange(10) * np.timedelta64(15, "m")
    mask = load_news_mask(p, ts, 1)
    assert np.flatnonzero(mask).tolist() == [3, 4, 5]


def test_barrier_uses_open_price_for_stop_loss_gap() -> None:
    alive = np.array([True, True, True])
    exit_price = np.array([100.0, 100.0, 100.0])
    _apply_barrier_step(
        open_price=np.array([95.0, 105.0, 100.0]),
        high=np.array([97.0, 106.0, 106.0]),
        low=np.array([94.0, 103.0, 98.0]),
        direction=np.array([1.0, -1.0, 1.0]),
        stop_price=np.array([98.0, 102.0, 99.0]),
        take_price=np.array([105.0, 95.0, 105.0]),
        alive=alive,
        exit_price=exit_price,
    )
    assert exit_price.tolist() == [95.0, 105.0, 99.0]
    assert alive.tolist() == [False, False, False]


def test_block_bootstrap_prefix_sum_matches_reference() -> None:
    n_days = 53
    timestamps = np.datetime64("2025-01-01", "D") + np.arange(n_days).astype("timedelta64[D]")
    signal_indices = np.arange(n_days)
    values = np.random.default_rng(7).normal(0.2, 1.0, n_days)
    reps = 200
    block_days = 20
    actual = _bootstrap_daily_blocks(
        values, signal_indices, timestamps, 0, reps, block_days, np.random.default_rng(421)
    )

    reference_rng = np.random.default_rng(421)
    observed = float(values.mean())
    blocks = int(np.ceil(n_days / block_days))
    starts = reference_rng.integers(0, n_days, size=(reps, blocks))
    offsets = np.arange(block_days)
    ix = ((starts[:, :, None] + offsets[None, None, :]) % n_days).reshape(reps, -1)[:, :n_days]
    sampled_sums = values[ix].sum(axis=1)
    means = sampled_sums / n_days
    centered = values - observed
    null_means = centered[ix].sum(axis=1) / n_days
    expected = (
        observed,
        float(np.nanquantile(means, 0.025)),
        float(np.nanquantile(means, 0.975)),
        float((1 + np.count_nonzero(null_means >= observed)) / (1 + reps)),
        float((1 + np.count_nonzero(null_means <= observed)) / (1 + reps)),
    )
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_grid_fails_closed_without_verified_cost_model() -> None:
    data = synthetic_data()
    cfg = EngineConfig(
        lookbacks=(3,),
        z_thresholds=(0.5,),
        take_profit_atr=(1.0,),
        stop_loss_atr=(1.0,),
        horizons=(4,),
        news_buffers_bars=(0, 1, 2),
        bootstrap_replicates=100,
        bootstrap_block_trading_days=5,
    )
    report = run_grid(data, cfg)
    assert report["status"] == "NO_TRADE_COST_AUDIT_UNVERIFIED"
    assert report["candidate_count"] == 2
    assert report["grid"]["news_buffers_evaluated"] == [0]
    assert report["grid"]["news_buffer_variants_collapsed"] is True
    assert {item["params"]["direction_mode"] for item in report["candidates"]} == {
        "FOLLOW_SIGNAL", "REVERSE_SIGNAL"
    }
    assert report["cost_model"]["verified"] is False
    assert all(item["net_expectancy"] is None for item in report["candidates"])
    assert len(report["paired_directional_comparisons"]) == 1
    paired = report["paired_directional_comparisons"][0]
    assert paired["status"] == "UNVERIFIED_COSTS"
    assert paired["net_expectancy_difference_follow_minus_reverse"] is None
    assert paired["gross_expectancy_difference_follow_minus_reverse"] is not None


def test_grid_rejects_signals_crossing_data_gaps() -> None:
    data = synthetic_data()
    data["timestamp"][300:] += np.timedelta64(2, "h")
    cfg = EngineConfig(
        lookbacks=(3,),
        z_thresholds=(0.5,),
        take_profit_atr=(1.0,),
        stop_loss_atr=(1.0,),
        horizons=(4,),
        news_buffers_bars=(0,),
        bootstrap_replicates=100,
        bootstrap_block_trading_days=5,
    )
    report = run_grid(data, cfg)
    assert report["rows"] == 600
    assert report["status"] == "NO_TRADE_COST_AUDIT_UNVERIFIED"
