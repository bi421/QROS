"""
Event Extractor — deterministic extraction of market events from OHLCV data.

Current implementation:
  - XAUUSD D1 SMA20/100 crossover events
  - Forward return outcomes at available horizons

Design principles:
  - Deterministic: same input -> same events
  - No future leakage: event context uses only data available at event time
  - Reproducible: all random seeds are fixed (none used in core extraction)
  - Transparent: every event is fully attributable
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from researchos.market_memory.event_schema import (
    CrossoverDirection,
    EventContext,
    EventType,
    MarketEvent,
    Session,
)
from researchos.market_memory.event_schema import (
    MarketRegime as MarketRegimeEnum,
)

# =============================================================================
# Indicator Computation (deterministic, no external libraries)
# =============================================================================


def _compute_sma(prices: list[float], period: int) -> list[float | None]:
    """Compute Simple Moving Average. Returns None for insufficient data."""
    if len(prices) < period:
        return [None] * len(prices)
    sma: list[float | None] = [None] * (period - 1)
    for i in range(period - 1, len(prices)):
        sma.append(sum(prices[i - period + 1 : i + 1]) / period)
    return sma


def _compute_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    """Compute Average True Range."""
    if len(closes) < period + 1:
        return [0.0] * len(closes)

    trs = [0.0]
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    atr: list[float] = [0.0] * period
    atr.append(sum(trs[1 : period + 1]) / period)
    for i in range(period + 1, len(trs)):
        atr.append((atr[-1] * (period - 1) + trs[i]) / period)
    return atr


def _compute_rsi(closes: list[float], period: int = 14) -> list[float]:
    """Compute Relative Strength Index."""
    if len(closes) < period + 1:
        return [50.0] * len(closes)

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    rsi: list[float] = [50.0] * period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100.0 - 100.0 / (1.0 + rs))
    return rsi


def _compute_macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[list[float], list[float], list[float]]:
    """Compute MACD line, signal line, and histogram."""
    if len(closes) < slow:
        return [0.0] * len(closes), [0.0] * len(closes), [0.0] * len(closes)

    # Compute EMAs
    def ema(prices: list[float], period: int) -> list[float]:
        k = 2.0 / (period + 1)
        e = [sum(prices[:period]) / period]
        for p in prices[period:]:
            e.append(p * k + e[-1] * (1 - k))
        return [None] * (period - 1) + e

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = [0.0] * len(closes)
    for i in range(len(closes)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]

    # Signal line
    valid_macd = [m for m in macd_line if m != 0.0 or macd_line.index(m) >= slow - 1]
    signal_line = [0.0] * len(closes)
    if len(valid_macd) >= signal:
        signal_valid_start = macd_line.index(valid_macd[0])
        ema_signal = ema(valid_macd, signal)
        for i, val in enumerate(ema_signal):
            if val is not None:
                signal_line[signal_valid_start + i] = val

    histogram = [macd_line[i] - signal_line[i] for i in range(len(closes))]
    return macd_line, signal_line, histogram


def _determine_session(timestamp: datetime) -> str:
    """Determine trading session from UTC timestamp."""
    hour = timestamp.hour
    if 0 <= hour < 8:
        return Session.ASIAN.value
    elif 8 <= hour < 16:
        return Session.EUROPEAN.value
    elif 12 <= hour < 21:
        return Session.OVERLAP.value
    else:
        return Session.US.value


def _compute_regime(sma_fast: float, sma_slow: float, atr: float, close: float) -> tuple[str, str]:
    """Compute market regime and volatility state."""
    if sma_fast == 0 or sma_slow == 0 or close == 0:
        return MarketRegimeEnum.UNKNOWN.value, "Unknown"

    # Trend direction
    if sma_fast > sma_slow:
        trend = "Bullish"
    elif sma_fast < sma_slow:
        trend = "Bearish"
    else:
        trend = "Neutral"

    # Volatility state
    atr_pct = (atr / close) * 100 if close != 0 else 0
    if atr_pct > 2.0:
        vol_state = "High"
    elif atr_pct > 1.0:
        vol_state = "Medium"
    else:
        vol_state = "Low"

    # Regime
    if abs(sma_fast - sma_slow) / sma_slow > 0.01:
        regime = MarketRegimeEnum.TRENDING_UP.value if trend == "Bullish" else MarketRegimeEnum.TRENDING_DOWN.value
    else:
        regime = MarketRegimeEnum.RANGING.value

    return regime, vol_state


# =============================================================================
# Data Loading
# =============================================================================


def load_xauusd_d1(csv_path: str = "data/curated/xauusd/xauusd_d1_2021_2025_mt5_final.csv") -> pl.DataFrame:
    """
    Load XAUUSD D1 data from CSV.

    Returns DataFrame with columns:
        timestamp, open, high, low, close, tick_volume
    """
    df = pl.read_csv(csv_path)
    df = df.with_columns(pl.concat_str([pl.col("Date"), pl.lit("T"), pl.col("Time")]).alias("timestamp"))
    df = df.with_columns(pl.col("timestamp").str.to_datetime("%Y.%m.%dT%H:%M:%S").alias("timestamp"))
    df = df.with_columns(
        pl.col("Open").alias("open"),
        pl.col("High").alias("high"),
        pl.col("Low").alias("low"),
        pl.col("Close").alias("close"),
        pl.col("tick_volume").alias("tick_volume"),
    )
    df = df.select(["timestamp", "open", "high", "low", "close", "tick_volume"]).sort("timestamp")
    return df


# =============================================================================
# Event Extraction
# =============================================================================


def extract_sma_crossover_events(
    df: pl.DataFrame,
    fast_period: int = 20,
    slow_period: int = 100,
    dataset_source: str = "xauusd_d1_2021_2025_mt5_final",
    seed: int = 42,
) -> list[MarketEvent]:
    """
    Extract SMA20/100 crossover events from XAUUSD D1 data.

    A crossover event occurs when the fast SMA crosses above (bullish)
    or below (bearish) the slow SMA.

    Args:
        df: DataFrame with columns [timestamp, open, high, low, close, tick_volume]
        fast_period: Fast SMA period (default 20)
        slow_period: Slow SMA period (default 100)
        dataset_source: Identifier for the source dataset
        seed: Random seed for reproducibility (unused in core extraction)

    Returns:
        List of MarketEvent objects, one per crossover.
    """
    if len(df) < slow_period + 1:
        raise ValueError(f"Insufficient data: need at least {slow_period + 1} bars, got {len(df)}")

    closes = df["close"].to_list()
    timestamps = df["timestamp"].to_list()
    highs = df["high"].to_list()
    lows = df["low"].to_list()
    volumes = df["tick_volume"].to_list()

    sma_fast = _compute_sma(closes, fast_period)
    sma_slow = _compute_sma(closes, slow_period)
    atr = _compute_atr(highs, lows, closes)
    rsi = _compute_rsi(closes)
    macd_line, macd_signal, macd_histogram = _compute_macd(closes)

    events = []
    for i in range(slow_period, len(df)):
        if sma_fast[i] is None or sma_slow[i] is None:
            continue
        if sma_fast[i - 1] is None or sma_slow[i - 1] is None:
            continue

        # Detect crossover
        prev_fast = sma_fast[i - 1]
        prev_slow = sma_slow[i - 1]
        curr_fast = sma_fast[i]
        curr_slow = sma_slow[i]

        direction = None
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            direction = CrossoverDirection.BULLISH
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            direction = CrossoverDirection.BEARISH

        if direction is None:
            continue

        # Event ID
        event_id = f"XAUUSD_D1_SMA{fast_period}_{slow_period}_{timestamps[i].strftime('%Y%m%d')}_{direction.value}"

        # Context
        regime, vol_state = _compute_regime(curr_fast, curr_slow, atr[i], closes[i])

        preceding_return_1d = (closes[i] - closes[i - 1]) / closes[i - 1] if i >= 1 else None
        preceding_return_3d = (closes[i] - closes[i - 3]) / closes[i - 3] if i >= 3 else None
        preceding_return_5d = (closes[i] - closes[i - 5]) / closes[i - 5] if i >= 5 else None

        context = EventContext(
            event_id=event_id,
            asset="XAUUSD",
            timeframe="D1",
            timestamp=timestamps[i],
            event_price=closes[i],
            open_price=df["open"][i],
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
            day_of_week=timestamps[i].weekday(),
            session=_determine_session(timestamps[i]),
            preceding_return_1d=preceding_return_1d,
            preceding_return_3d=preceding_return_3d,
            preceding_return_5d=preceding_return_5d,
        )

        event = MarketEvent(
            event_id=event_id,
            asset="XAUUSD",
            timeframe="D1",
            event_type=EventType.SMA_CROSSOVER.value,
            direction=direction.value,
            timestamp=timestamps[i],
            event_price=closes[i],
            context=context,
            dataset_source=dataset_source,
            computation_method=f"SMA{fast_period}/{slow_period}_crossover",
            seed=seed,
        )
        events.append(event)

    return events
