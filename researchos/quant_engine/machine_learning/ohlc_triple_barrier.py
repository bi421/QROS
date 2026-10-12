"""OHLC-aware, deterministic XAUUSD triple-barrier research labels.

Labels are supervised outcomes only. This module does not generate signals,
probabilities, recommendations, or orders. The decision at bar i uses ATR and
direction at i, enters at bar i+1 open, then scans OHLC from that entry bar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from researchos.orchestration.xauusd_research import (
    OutcomeLabel,
    OutcomeSpec,
)


@dataclass(frozen=True)
class OHLCBar:
    """One completed OHLC bar."""

    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class OHLCOutcome:
    """Outcome for one decision index; None means not safely labelable."""

    decision_index: int
    entry_index: int | None
    direction: int
    label: OutcomeLabel | None
    reason_code: str


def _finite(value: object, name: str, index: int) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name}[{index}] must be finite numeric data")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}[{index}] must be finite numeric data") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{name}[{index}] must be finite numeric data")
    return parsed


def _validate_bars(bars: Sequence[OHLCBar]) -> None:
    for i, bar in enumerate(bars):
        if not isinstance(bar, OHLCBar):
            raise ValueError(f"bars[{i}] must be an OHLCBar")
        o = _finite(bar.open, "open", i)
        h = _finite(bar.high, "high", i)
        low = _finite(bar.low, "low", i)
        c = _finite(bar.close, "close", i)
        if min(o, h, low, c) <= 0:
            raise ValueError(f"bars[{i}] prices must be positive")
        if h < max(o, c, low) or low > min(o, c):
            raise ValueError(f"bars[{i}] has inconsistent OHLC bounds")


def label_ohlc_outcomes(
    bars: Sequence[OHLCBar],
    directions: Sequence[int],
    atr_values: Sequence[float | None],
    spec: OutcomeSpec | None = None,
) -> tuple[OHLCOutcome, ...]:
    """Label decisions using next-bar-open entry and OHLC barrier touches.

    directions[i] and atr_values[i] must be known at decision bar i.
    The entry is bar i+1 open. That entry bar counts as holding bar 1.
    A label is emitted only when the complete holding horizon is present.
    If TP and SL are both touched in one candle, EXCLUDE returns no label;
    CONSERVATIVE_SL_FIRST labels STOP_LOSS. Missing/invalid ATR makes only
    that decision unlabelable; malformed OHLC input rejects the whole call.
    """
    chosen = spec or OutcomeSpec()
    _validate_bars(bars)
    if len(directions) != len(bars) or len(atr_values) != len(bars):
        raise ValueError("bars, directions, and atr_values must have equal lengths")

    outputs: list[OHLCOutcome] = []
    count = len(bars)
    for i, direction in enumerate(directions):
        if isinstance(direction, bool) or direction not in (-1, 0, 1):
            raise ValueError(f"directions[{i}] must be -1, 0, or 1")

        entry_index = i + 1
        if direction == 0:
            outputs.append(OHLCOutcome(i, entry_index if entry_index < count else None,
                                       direction, None, "NEUTRAL_DIRECTION"))
            continue
        if entry_index >= count:
            outputs.append(OHLCOutcome(i, None, direction, None, "ENTRY_BAR_MISSING"))
            continue

        raw_atr = atr_values[i]
        if raw_atr is None:
            outputs.append(OHLCOutcome(i, entry_index, direction, None, "ATR_MISSING"))
            continue
        try:
            atr = _finite(raw_atr, "atr_values", i)
        except ValueError:
            outputs.append(OHLCOutcome(i, entry_index, direction, None, "ATR_INVALID"))
            continue
        if atr <= 0:
            outputs.append(OHLCOutcome(i, entry_index, direction, None, "ATR_INVALID"))
            continue

        final_index = entry_index + chosen.max_holding_bars - 1
        if final_index >= count:
            outputs.append(OHLCOutcome(i, entry_index, direction, None, "HORIZON_INCOMPLETE"))
            continue

        entry_price = bars[entry_index].open
        if direction == 1:
            take_profit = entry_price + chosen.take_profit_atr * atr
            stop_loss = entry_price - chosen.stop_loss_atr * atr
        else:
            take_profit = entry_price - chosen.take_profit_atr * atr
            stop_loss = entry_price + chosen.stop_loss_atr * atr

        outcome: OutcomeLabel | None = None
        reason = "HORIZON_TIMEOUT"
        for j in range(entry_index, final_index + 1):
            bar = bars[j]
            if direction == 1:
                hit_tp = bar.high >= take_profit
                hit_sl = bar.low <= stop_loss
            else:
                hit_tp = bar.low <= take_profit
                hit_sl = bar.high >= stop_loss

            if hit_tp and hit_sl:
                if chosen.ambiguous_touch_policy == "EXCLUDE":
                    reason = "AMBIGUOUS_SAME_BAR_TOUCH"
                else:
                    outcome = OutcomeLabel.STOP_LOSS
                    reason = "STOP_LOSS_CONSERVATIVE_AMBIGUOUS"
                break
            if hit_sl:
                outcome = OutcomeLabel.STOP_LOSS
                reason = "STOP_LOSS_FIRST_TOUCH"
                break
            if hit_tp:
                outcome = OutcomeLabel.TAKE_PROFIT
                reason = "TAKE_PROFIT_FIRST_TOUCH"
                break
        else:
            outcome = OutcomeLabel.TIMEOUT

        outputs.append(OHLCOutcome(i, entry_index, direction, outcome, reason))

    return tuple(outputs)


__all__ = ["OHLCBar", "OHLCOutcome", "label_ohlc_outcomes"]
