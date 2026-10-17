from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from researchos.orchestration.vectorized_backtest import (
    EngineConfig,
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
