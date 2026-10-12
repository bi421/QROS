"""OHLC-aware, deterministic XAUUSD triple-barrier research labels.

This additive research labeler does not alter existing close-only label
functions, predict probabilities, or execute trades. Labels require a fully
observed forward window; incomplete and ambiguous EXCLUDE windows return None.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from researchos.orchestration.xauusd_research import OutcomeLabel, OutcomeSpec


@dataclass(frozen=True)
class OHLCBar:
    """One timezone-aware OHLC candle with strictly positive prices."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.timestamp, datetime)
            or self.timestamp.tzinfo is None
            or self.timestamp.utcoffset() is None
        ):
            raise ValueError("bar timestamp must be timezone-aware")
        prices: dict[str, float] = {}
        for name in ("open", "high", "low", "close"):
            value = getattr(self, name)
            if isinstance(value, bool):
                raise ValueError(f"{name} must be finite and positive")
            try:
                numeric = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"{name} must be finite and positive") from exc
            if not math.isfinite(numeric) or numeric <= 0:
                raise ValueError(f"{name} must be finite and positive")
            prices[name] = numeric
        if prices["high"] < max(prices["open"], prices["close"]):
            raise ValueError("high must be >= open and close")
        if prices["low"] > min(prices["open"], prices["close"]):
            raise ValueError("low must be <= open and close")
        if prices["high"] < prices["low"]:
            raise ValueError("high must be >= low")


@dataclass(frozen=True)
class OHLCBarrierLabel:
    """Auditable result for one signal bar; no probability is implied."""

    event_time: datetime
    entry_time: datetime
    entry_price: float
    direction: int
    outcome: OutcomeLabel
    exit_time: datetime
    exit_price: float
    bars_held: int
    outcome_spec_version: str


def label_ohlc_triple_barrier(
    bars: Sequence[OHLCBar],
    directions: Sequence[int | None],
    atr: Sequence[float | None],
    spec: OutcomeSpec | None = None,
) -> list[OHLCBarrierLabel | None]:
    """Label signal bars using next-bar-open entry and OHLC barrier touches.

    directions[i] is +1 for long, -1 for short, or None for no signal.
    atr[i] must be known at the signal bar close, not a future value. A complete
    outcome needs the next bar plus max_holding_bars - 1 more bars. If a single
    bar touches both TP and SL, EXCLUDE returns None and CONSERVATIVE_SL_FIRST
    labels STOP_LOSS. Opening gaps are checked before intrabar extremes. This
    historical convention is not a promise of executable fills.
    """
    selected = spec or OutcomeSpec()
    if len(directions) != len(bars) or len(atr) != len(bars):
        raise ValueError("bars, directions, and atr must have equal lengths")
    for previous, current in zip(bars, bars[1:]):
        if current.timestamp <= previous.timestamp:
            raise ValueError("bar timestamps must be strictly increasing")

    normalized_atr: list[float | None] = []
    for value in atr:
        if value is None:
            normalized_atr.append(None)
            continue
        if isinstance(value, bool):
            raise ValueError("ATR values must be finite and positive or None")
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("ATR values must be finite and positive or None") from exc
        if not math.isfinite(numeric) or numeric <= 0:
            raise ValueError("ATR values must be finite and positive or None")
        normalized_atr.append(numeric)

    for direction in directions:
        if direction is not None and (
            isinstance(direction, bool) or direction not in (-1, 1)
        ):
            raise ValueError("directions must be -1, 1, or None")

    labels: list[OHLCBarrierLabel | None] = [None] * len(bars)
    horizon = selected.max_holding_bars
    for index, direction in enumerate(directions):
        if direction is None:
            continue
        end_index = index + horizon
        if end_index >= len(bars):
            continue
        event_atr = normalized_atr[index]
        if event_atr is None:
            continue

        entry_index = index + 1
        entry_bar = bars[entry_index]
        entry = float(entry_bar.open)
        if direction == 1:
            take_profit = entry + selected.take_profit_atr * event_atr
            stop_loss = entry - selected.stop_loss_atr * event_atr
        else:
            take_profit = entry - selected.take_profit_atr * event_atr
            stop_loss = entry + selected.stop_loss_atr * event_atr

        resolved: OHLCBarrierLabel | None = None
        for bar_index in range(entry_index, end_index + 1):
            bar = bars[bar_index]
            if direction == 1:
                open_tp = bar.open >= take_profit
                open_sl = bar.open <= stop_loss
                hit_tp = bar.high >= take_profit
                hit_sl = bar.low <= stop_loss
            else:
                open_tp = bar.open <= take_profit
                open_sl = bar.open >= stop_loss
                hit_tp = bar.low <= take_profit
                hit_sl = bar.high >= stop_loss

            if open_tp:
                outcome, exit_price = OutcomeLabel.TAKE_PROFIT, float(bar.open)
            elif open_sl:
                outcome, exit_price = OutcomeLabel.STOP_LOSS, float(bar.open)
            elif hit_tp and hit_sl:
                if selected.ambiguous_touch_policy == "EXCLUDE":
                    resolved = None
                    break
                outcome, exit_price = OutcomeLabel.STOP_LOSS, stop_loss
            elif hit_tp:
                outcome, exit_price = OutcomeLabel.TAKE_PROFIT, take_profit
            elif hit_sl:
                outcome, exit_price = OutcomeLabel.STOP_LOSS, stop_loss
            elif bar_index == end_index:
                outcome, exit_price = OutcomeLabel.TIMEOUT, float(bar.close)
            else:
                continue

            resolved = OHLCBarrierLabel(
                event_time=bars[index].timestamp,
                entry_time=entry_bar.timestamp,
                entry_price=entry,
                direction=direction,
                outcome=outcome,
                exit_time=bar.timestamp,
                exit_price=float(exit_price),
                bars_held=bar_index - entry_index + 1,
                outcome_spec_version=selected.version,
            )
            break
        labels[index] = resolved
    return labels


__all__ = ["OHLCBar", "OHLCBarrierLabel", "label_ohlc_triple_barrier"]
