from __future__ import annotations

import pandas as pd
import pytest

from scripts.biberion_shotgun_backtest import run_backtest


def _bars(n: int = 100) -> pd.DataFrame:
    timestamps = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    rows = []
    for i, ts in enumerate(timestamps):
        close = 100.0 + i * 0.2
        rows.append({
            "timestamp": ts, "symbol": "A", "open": close - 0.05,
            "high": close + 0.2, "low": close - 0.2, "close": close,
            "volume": 100.0 if i % 10 else 500.0,
            "benchmark_close": 1000.0 + i * 0.5, "flow_imbalance": 0.5,
        })
    return pd.DataFrame(rows)


def test_backtest_is_deterministic_and_hashes_input() -> None:
    data = _bars()
    a = run_backtest(data, volume_window=10, slow=5, fast=2)
    b = run_backtest(data, volume_window=10, slow=5, fast=2)
    assert a["dataset_sha256"] == b["dataset_sha256"]
    assert a["result_sha256"] == b["result_sha256"]
    assert a["summary"]["live_edge_proven"] is False


def test_duplicate_bar_is_rejected() -> None:
    data = _bars(60)
    data = pd.concat([data, data.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        run_backtest(data, volume_window=10, slow=5, fast=2)


def test_no_signal_warmup_means_no_lookahead_entry() -> None:
    data = _bars(20)
    result = run_backtest(data, volume_window=10, slow=5, fast=2)
    assert result["summary"]["trades"] == 0
