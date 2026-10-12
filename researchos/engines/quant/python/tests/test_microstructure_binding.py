"""Optional integration tests for the separately built microstructure extension."""

from __future__ import annotations

import numpy as np
import pytest

microstructure = pytest.importorskip("cpp_quant_engine.qros_microstructure")


def test_timed_market_event_keeps_event_and_ingest_times_separate() -> None:
    event = microstructure.TimedMarketEvent()
    event.symbol = "XAUUSD"
    event.source_id = "fixture-feed"
    event.venue = "fixture"
    event.kind = microstructure.MarketEventKind.TRADE
    event.sequence = 7
    event.event_time_ns = 1_000
    event.ingest_time_ns = 1_250

    assert event.source_id == "fixture-feed"
    assert event.venue == "fixture"
    assert event.kind == microstructure.MarketEventKind.TRADE
    assert event.event_time_ns == 1_000
    assert event.ingest_time_ns == 1_250
    assert event.ingest_time_ns - event.event_time_ns == 250


def test_numpy_inputs_work_with_ofi_kernel() -> None:
    bid_price = np.ascontiguousarray([100.0, 100.0], dtype=np.float64)
    bid_size = np.ascontiguousarray([10.0, 12.0], dtype=np.float64)
    ask_price = np.ascontiguousarray([100.2, 100.2], dtype=np.float64)
    ask_size = np.ascontiguousarray([9.0, 8.0], dtype=np.float64)

    result = microstructure.order_flow_imbalance(
        bid_price, bid_size, ask_price, ask_size
    )

    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float64
    np.testing.assert_array_equal(result, np.array([0.0, 3.0]))


def test_sweep_kernel_returns_owned_numpy_masks() -> None:
    high = np.ascontiguousarray([101.0], dtype=np.float64)
    low = np.ascontiguousarray([99.5], dtype=np.float64)
    close = np.ascontiguousarray([99.8], dtype=np.float64)

    above, below = microstructure.detect_liquidity_sweeps(
        high, low, close, 100.0
    )

    np.testing.assert_array_equal(above, np.array([1], dtype=np.uint8))
    np.testing.assert_array_equal(below, np.array([0], dtype=np.uint8))


def test_volume_profile_summary_is_stable() -> None:
    prices = np.ascontiguousarray([100.0, 100.0, 101.0, 102.0], dtype=np.float64)
    volumes = np.ascontiguousarray([2.0, 3.0, 4.0, 1.0], dtype=np.float64)

    result = microstructure.volume_profile_summary(prices, volumes, 1.0, 0.70)

    assert result["poc_price"] == 100.0
    assert result["value_area_low"] == 100.0
    assert result["value_area_high"] == 101.0
    assert result["total_volume"] == 10.0
