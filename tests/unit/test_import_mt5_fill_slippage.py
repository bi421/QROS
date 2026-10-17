from __future__ import annotations

import polars as pl
import pytest

from scripts.import_mt5_fill_slippage import apply_slippage_benchmarks


def _frame():
    return pl.DataFrame({
        "timestamp": ["2026-10-17T10:00:00+00:00"] * 4,
        "symbol": ["xauusd"] * 4,
        "order_type": ["market_entry", "market_exit", "tp_limit", "sl_stop"],
        "side": ["BUY", "SELL", "BUY", "SELL"],
        "requested_price": [None, None, 2501.0, 2500.0],
        "fill_price": [2500.12, 2500.08, 2501.02, 2499.80],
        "volume": [0.01] * 4,
        "order_id": ["1", "2", "3", "4"],
        "deal_id": ["11", "22", "33", "44"],
        "quote_bid": [2500.0, 2500.1, 2500.9, 2499.9],
        "quote_ask": [2500.1, 2500.2, 2501.0, 2500.0],
    })


def test_market_slippage_uses_request_time_executable_side_and_signed_adverse_value():
    result = apply_slippage_benchmarks(_frame())
    assert result["benchmark_price"].to_list() == pytest.approx([2500.1, 2500.1, 2501.0, 2500.0])
    assert result["adverse_slippage_price_units"].to_list() == pytest.approx([0.02, 0.02, 0.02, 0.20])


def test_limit_and_stop_fills_require_requested_trigger_price():
    frame = _frame().with_columns(
        pl.when(pl.col("order_type") == "sl_stop")
        .then(None)
        .otherwise(pl.col("requested_price"))
        .alias("requested_price")
    )
    with pytest.raises(ValueError, match="MISSING_BENCHMARK"):
        apply_slippage_benchmarks(frame)
