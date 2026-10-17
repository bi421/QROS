from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from researchos.orchestration.vectorized_backtest import (
    EngineConfig,
    _apply_barrier_step,
    _atr,
    _causal_signal_score,
    _validate_backtest_data,
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


def test_grid_fails_closed_without_verified_cost_model() -> None:
    data = synthetic_data()
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
    assert report["status"] == "NO_TRADE_COST_AUDIT_UNVERIFIED"
    assert report["candidate_count"] == 1
    assert report["cost_model"]["verified"] is False
    assert report["candidates"][0]["net_expectancy"] is None


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


def test_csv_loader_rejects_out_of_order_source_rows(tmp_path: Path) -> None:
    p = tmp_path / "out_of_order.csv"
    p.write_text(
        "2025.01.01 00:15,100,101,99,100.5,10,20\n2025.01.01 00:00,100.5,102,100,101.5,11,21\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Out-of-order timestamps"):
        load_ohlcv_csv(p)


def test_direct_backtest_input_fails_closed_on_duplicate_timestamps() -> None:
    data = synthetic_data()
    data["timestamp"][200] = data["timestamp"][199]
    with pytest.raises(ValueError, match="strictly increasing and unique"):
        _validate_backtest_data(data)


def test_causal_signal_scores_are_invariant_to_future_data_perturbation() -> None:
    data = synthetic_data(400)
    close = data["close"].copy()
    atr = _atr(data["high"], data["low"], close)
    baseline = _causal_signal_score(close, atr, data["timestamp"], lookback=8)

    cutoff = 250
    perturbed_close = close.copy()
    perturbed_close[cutoff + 1 :] += np.linspace(10.0, 100.0, len(close) - cutoff - 1)
    perturbed_high = data["high"].copy()
    perturbed_low = data["low"].copy()
    perturbed_high[cutoff + 1 :] += 120.0
    perturbed_low[cutoff + 1 :] += 5.0
    perturbed_atr = _atr(perturbed_high, perturbed_low, perturbed_close)
    changed = _causal_signal_score(perturbed_close, perturbed_atr, data["timestamp"], lookback=8)

    np.testing.assert_allclose(baseline[: cutoff + 1], changed[: cutoff + 1], equal_nan=True)
    assert not np.allclose(baseline[cutoff + 1 :], changed[cutoff + 1 :], equal_nan=True)


def test_signal_score_invalidates_lookback_window_crossing_a_gap() -> None:
    data = synthetic_data(200)
    timestamps = data["timestamp"].copy()
    timestamps[100:] += np.timedelta64(60, "m")
    atr = _atr(data["high"], data["low"], data["close"])
    score = _causal_signal_score(data["close"], atr, timestamps, lookback=8)
    assert np.isnan(score[100:108]).all()
    assert np.isfinite(score[110])


def test_cost_model_boolean_alone_does_not_certify_costs() -> None:
    data = synthetic_data()
    cfg = EngineConfig(
        lookbacks=(3,),
        z_thresholds=(0.5,),
        take_profit_atr=(1.0,),
        stop_loss_atr=(1.0,),
        horizons=(4,),
        news_buffers_bars=(0,),
        bootstrap_replicates=100,
        bootstrap_block_trading_days=5,
        base_spread_price=0.2,
        cost_alpha_price=0.1,
        commission_roundtrip_price=0.1,
        cost_model_verified=True,
        cost_evidence_sha256=None,
    )
    report = run_grid(data, cfg)
    assert report["cost_model"]["configured"] is True
    assert report["cost_model"]["verified"] is False
    assert report["status"] == "NO_TRADE_COST_AUDIT_UNVERIFIED"
