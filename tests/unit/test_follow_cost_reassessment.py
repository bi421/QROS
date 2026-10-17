from __future__ import annotations

import numpy as np
import polars as pl

from scripts.reassess_follow_pairs_with_trade_costs import (
    bootstrap_trade_blocks,
    build_trade_arrays,
    overlap_diagnostics,
    resolve_exit_m1_quotes,
    validate_gross_pair_consistency,
)


def test_close_signal_enters_next_m15_bar_open_not_signal_bar_close():
    timestamps = np.datetime64("2021-01-01T00:00", "ns") + np.arange(6) * np.timedelta64(15, "m")
    bars = pl.DataFrame({
        "entry_spread": [4.0] * 6,
        "entry_m1_ts": timestamps,
    })
    opens = np.array([100.0, 101.0, 102.5, 103.0, 104.0, 105.0])
    highs = opens + 0.2
    lows = opens - 0.2
    closes = opens + 0.1
    atr = np.ones(6, dtype=float)
    trades = build_trade_arrays(
        bars, np.array([1]), np.array([1.0]), 100.0, 100.0, 2, atr,
        opens, highs, lows, closes, timestamps,
    )
    assert trades["signal_ix"].tolist() == [1]
    assert trades["entry_ix"].tolist() == [2]
    assert trades["entry_price"].tolist() == [102.5]
    assert trades["entry_bar_ts"][0] == timestamps[2]
    assert trades["entry_ts"][0] == timestamps[2]


def test_tp_sl_exit_spread_uses_first_m1_minute_that_hits_selected_barrier():
    base = np.datetime64("2021-01-01T00:00", "ns")
    minute_ts = base + np.arange(15) * np.timedelta64(1, "m")
    low = np.full(15, 100.0)
    low[4] = 98.5
    m1 = pl.DataFrame({
        "timestamp": minute_ts,
        "high": np.full(15, 101.0),
        "low": low,
        "spread": np.arange(1, 16, dtype=float),
    })
    trades = {
        "exit_ix": np.array([0]),
        "exit_reason": np.array([1], dtype=np.int8),
        "direction": np.array([1], dtype=np.int8),
        "sl_price": np.array([99.0]),
        "tp_price": np.array([102.0]),
    }
    spread, exit_ts, exact = resolve_exit_m1_quotes(trades, m1, np.array([base]))
    assert exact.tolist() == [True]
    assert spread.tolist() == [5.0]
    assert exit_ts[0] == minute_ts[4]


def test_incomplete_tp_sl_bucket_is_excluded_not_given_proxy_spread():
    base = np.datetime64("2021-01-01T00:00", "ns")
    minute_ts = base + np.array([0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]) * np.timedelta64(1, "m")
    low = np.full(14, 100.0)
    low[3] = 98.5
    m1 = pl.DataFrame({
        "timestamp": minute_ts,
        "high": np.full(14, 101.0),
        "low": low,
        "spread": np.arange(1, 15, dtype=float),
    })
    trades = {
        "exit_ix": np.array([0]),
        "exit_reason": np.array([1], dtype=np.int8),
        "direction": np.array([1], dtype=np.int8),
        "sl_price": np.array([99.0]),
        "tp_price": np.array([102.0]),
    }
    spread, exit_ts, exact = resolve_exit_m1_quotes(trades, m1, np.array([base]))
    assert exact.tolist() == [False]
    assert np.isnan(spread[0])
    assert np.isnat(exit_ts[0])


def test_trade_overlap_diagnostics_report_overlaps_and_peak_positions():
    result = overlap_diagnostics(np.array([1, 2, 6]), np.array([4, 5, 7]))
    assert result["trade_count"] == 3
    assert result["overlapping_trade_count"] == 1
    assert result["peak_concurrent_trades"] == 2


def test_original_gross_artifact_pair_differences_match_directional_candidates():
    common = {
        "lookback": 4, "z": 0.5, "tp_atr": 1.0, "sl_atr": 0.75,
        "horizon": 8, "news_buffer_bars": 0,
    }
    candidates = [
        {"params": {**common, "direction_mode": "FOLLOW_SIGNAL"}, "gross_expectancy": 2.25},
        {"params": {**common, "direction_mode": "REVERSE_SIGNAL"}, "gross_expectancy": 1.75},
    ]
    pairs = [{
        "params": common,
        "gross_expectancy_difference_follow_minus_reverse": 0.5,
    }]
    result = validate_gross_pair_consistency(candidates, pairs)
    assert result["status"] == "PASS"
    assert result["paired_comparisons"] == 1
    assert result["max_abs_difference_error"] == 0.0


def test_block_bootstrap_is_deterministic_and_returns_finite_intervals():
    values = np.column_stack((np.arange(80, dtype=float), np.arange(80, dtype=float) - 2))
    a = bootstrap_trade_blocks(values, block_length=8, reps=100, rng=np.random.default_rng(42))
    b = bootstrap_trade_blocks(values, block_length=8, reps=100, rng=np.random.default_rng(42))
    for left, right in zip(a, b, strict=True):
        assert np.allclose(left, right)
    assert a[1].shape == (2,)
    assert a[2].shape == (2,)
