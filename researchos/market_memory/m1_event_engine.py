"""Deterministic XAUUSD M1 event extraction."""
from __future__ import annotations

from bisect import bisect_right
from datetime import timedelta

import polars as pl

from researchos.market_memory.event_extractor import (
    _compute_atr,
    _compute_macd,
    _compute_regime,
    _compute_rsi,
    _compute_sma,
    _determine_session,
)
from researchos.market_memory.event_schema import (
    CrossoverDirection,
    EventContext,
    EventType,
    MarketEvent,
)


def extract_xauusd_m1_sma_crossover_events(
    df: pl.DataFrame,
    fast_period: int = 20,
    slow_period: int = 100,
    dataset_source: str = "xauusd_m1_mt5",
    seed: int = 42,
) -> list[MarketEvent]:
    """Extract SMA crossover events using only bars available at event time."""
    required = {"timestamp", "open", "high", "low", "close", "tick_volume"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"df missing columns: {sorted(missing)}")
    if fast_period < 1 or slow_period <= fast_period:
        raise ValueError("periods must satisfy 1 <= fast_period < slow_period")
    if len(df) < slow_period + 1:
        raise ValueError(f"Insufficient data: need at least {slow_period + 1} bars, got {len(df)}")

    frame = df.sort("timestamp")
    timestamps = frame["timestamp"].to_list()
    opens = frame["open"].to_list()
    highs = frame["high"].to_list()
    lows = frame["low"].to_list()
    closes = frame["close"].to_list()
    volumes = frame["tick_volume"].to_list()

    sma_fast = _compute_sma(closes, fast_period)
    sma_slow = _compute_sma(closes, slow_period)
    atr = _compute_atr(highs, lows, closes)
    rsi = _compute_rsi(closes)
    macd_line, macd_signal, macd_histogram = _compute_macd(closes)

    events: list[MarketEvent] = []
    for i in range(slow_period, len(frame)):
        prev_fast, prev_slow = sma_fast[i - 1], sma_slow[i - 1]
        curr_fast, curr_slow = sma_fast[i], sma_slow[i]
        if prev_fast is None or prev_slow is None or curr_fast is None or curr_slow is None:
            continue

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            direction = CrossoverDirection.BULLISH.value
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            direction = CrossoverDirection.BEARISH.value
        else:
            continue

        timestamp = timestamps[i]
        event_id = f"XAUUSD_M1_SMA{fast_period}_{slow_period}_{timestamp.strftime('%Y%m%dT%H%M%S')}_{direction}"
        regime, vol_state = _compute_regime(curr_fast, curr_slow, atr[i], closes[i])

        def preceding_return(days: int) -> float | None:
            target = timestamp - timedelta(days=days)
            j = bisect_right(timestamps, target, hi=i) - 1
            if j < 0:
                return None
            close_now = float(closes[i])
            close_then = float(closes[j])
            if close_then == 0.0:
                return None
            return (close_now - close_then) / close_then

        context = EventContext(
            event_id=event_id,
            asset="XAUUSD",
            timeframe="M1",
            timestamp=timestamp,
            event_price=closes[i],
            open_price=opens[i],
            high_price=highs[i],
            low_price=lows[i],
            close_price=closes[i],
            tick_volume=int(volumes[i]),
            sma_fast=curr_fast,
            sma_slow=curr_slow,
            atr=atr[i],
            rsi=rsi[i] if rsi[i] is not None else 50.0,
            macd_line=macd_line[i],
            macd_signal=macd_signal[i],
            macd_histogram=macd_histogram[i],
            market_regime=regime,
            volatility_state=vol_state,
            day_of_week=timestamp.weekday(),
            session=_determine_session(timestamp),
            preceding_return_1d=preceding_return(1),
            preceding_return_3d=preceding_return(3),
            preceding_return_5d=preceding_return(5),
        )
        events.append(
            MarketEvent(
                event_id=event_id,
                asset="XAUUSD",
                timeframe="M1",
                event_type=EventType.SMA_CROSSOVER.value,
                direction=direction,
                timestamp=timestamp,
                event_price=closes[i],
                context=context,
                dataset_source=dataset_source,
                computation_method=f"M1_SMA{fast_period}/{slow_period}_crossover",
                seed=seed,
            )
        )
    return events
