"""Deterministic, causal OHLC market-structure event detection.

This module detects confirmed swing points and BOS/CHoCH events. It does not
place orders, produce trade recommendations, or claim predictive edge.
A pivot is available only after its right-hand confirmation window has closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import product
from typing import Literal, Sequence

import numpy as np
import numpy.typing as npt

from researchos.quant_engine.technical.market_structure_definition import StructureDefinition

BreakBasis = Literal["wick", "close"]
SwingKind = Literal["swing_high", "swing_low"]
StructureKind = Literal["BOS", "CHOCH"]
Direction = Literal["bullish", "bearish"]


@dataclass(frozen=True, slots=True)
class MarketStructureConfig:
    """One fully specified market-structure definition."""

    swing_window: int = 3
    break_basis: BreakBasis = "close"
    confirmation_bars: int = 1
    break_buffer_atr: float = 0.0
    atr_period: int = 14

    def __post_init__(self) -> None:
        if isinstance(self.swing_window, bool) or not isinstance(self.swing_window, int) or self.swing_window < 1:
            raise ValueError("swing_window must be an integer >= 1")
        if self.break_basis not in ("wick", "close"):
            raise ValueError("break_basis must be 'wick' or 'close'")
        if (
            isinstance(self.confirmation_bars, bool)
            or not isinstance(self.confirmation_bars, int)
            or self.confirmation_bars < 1
        ):
            raise ValueError("confirmation_bars must be an integer >= 1")
        if (
            isinstance(self.atr_period, bool)
            or not isinstance(self.atr_period, int)
            or self.atr_period < 1
        ):
            raise ValueError("atr_period must be an integer >= 1")
        if (
            isinstance(self.break_buffer_atr, bool)
            or not isinstance(self.break_buffer_atr, (int, float, np.integer, np.floating))
            or not np.isfinite(self.break_buffer_atr)
            or self.break_buffer_atr < 0
        ):
            raise ValueError("break_buffer_atr must be finite and >= 0")

    @property
    def variant_id(self) -> str:
        buffer_bps = int(round(self.break_buffer_atr * 10_000))
        return (
            f"sw{self.swing_window:02d}_{self.break_basis}"
            f"_c{self.confirmation_bars}_atr{buffer_bps:04d}"
        )

    def to_definition(self) -> StructureDefinition:
        return StructureDefinition(
            swing_window=self.swing_window,
            break_basis=self.break_basis,
            confirmation_bars=self.confirmation_bars,
            break_buffer_atr=float(self.break_buffer_atr),
            atr_period=self.atr_period,
        )


@dataclass(frozen=True, slots=True)
class SwingPoint:
    kind: SwingKind
    pivot_index: int
    confirmed_index: int
    price: float


@dataclass(frozen=True, slots=True)
class StructureBreak:
    kind: StructureKind
    direction: Direction
    level: float
    pivot_index: int
    pivot_confirmed_index: int
    break_index: int
    break_price: float
    variant_id: str
    definition_id: str


@dataclass(frozen=True, slots=True)
class MarketStructureResult:
    variant_id: str
    definition_id: str
    rows: int
    swings: tuple[SwingPoint, ...]
    breaks: tuple[StructureBreak, ...]
    ambiguous_break_indices: tuple[int, ...]
    gap_indices: tuple[int, ...]
    final_trend: Literal["unknown", "bullish", "bearish"]


def market_structure_variants() -> tuple[MarketStructureConfig, ...]:
    """Return a transparent 56-definition screening grid (7 x 2 x 2 x 2).

    The grid is a QROS research design, not a claim that it duplicates a
    third-party video's exact 56 definitions.
    """
    configs = (
        MarketStructureConfig(
            swing_window=window,
            break_basis=basis,
            confirmation_bars=confirmations,
            break_buffer_atr=buffer,
        )
        for window, basis, confirmations, buffer in product(
            (2, 3, 4, 5, 6, 8, 10),
            ("wick", "close"),
            (1, 2),
            (0.0, 0.05),
        )
    )
    return tuple(configs)


def _validate_ohlc(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    high_array = np.asarray(high, dtype=np.float64)
    low_array = np.asarray(low, dtype=np.float64)
    close_array = np.asarray(close, dtype=np.float64)

    if any(array.ndim != 1 for array in (high_array, low_array, close_array)):
        raise ValueError("high, low, and close must be one-dimensional")
    if not (len(high_array) == len(low_array) == len(close_array)):
        raise ValueError("high, low, and close must have equal lengths")
    if not len(close_array):
        raise ValueError("OHLC input must contain at least one row")
    if not all(
        np.isfinite(array).all()
        for array in (high_array, low_array, close_array)
    ):
        raise ValueError("OHLC input contains non-finite values")
    if np.any(high_array < low_array):
        raise ValueError("high must be >= low")
    if np.any(high_array < close_array) or np.any(low_array > close_array):
        raise ValueError("close must lie within each bar's high/low range")

    return high_array, low_array, close_array


def _validate_utc_timestamps(
    timestamps: Sequence[datetime] | None,
    expected_rows: int,
) -> npt.NDArray[np.bool_]:
    if timestamps is None:
        raise ValueError("timezone-aware UTC timestamps are required")
    if len(timestamps) != expected_rows:
        raise ValueError("timestamps must have the same length as OHLC input")

    epochs: list[int] = []
    previous: int | None = None
    for index, value in enumerate(timestamps):
        if not isinstance(value, datetime):
            raise ValueError("timestamps must contain datetime values")
        if (
            value.tzinfo is None
            or value.utcoffset() != timedelta(0)
            or value.tzname() not in ("UTC", "Etc/UTC")
        ):
            raise ValueError("timestamps must be timezone-aware UTC")
        if value.second != 0 or value.microsecond != 0:
            raise ValueError("M1 timestamps must be aligned to whole minutes")
        epoch = int(value.timestamp())
        if previous is not None and epoch <= previous:
            raise ValueError("timestamps must be unique and strictly increasing")
        epochs.append(epoch)
        previous = epoch

    gap_before = np.zeros(expected_rows, dtype=np.bool_)
    if expected_rows > 1:
        gap_before[1:] = np.diff(np.asarray(epochs, dtype=np.int64)) != 60
    return gap_before


def _atr(
    high: npt.NDArray[np.float64],
    low: npt.NDArray[np.float64],
    close: npt.NDArray[np.float64],
    period: int,
) -> npt.NDArray[np.float64]:
    previous_close = np.r_[close[0], close[:-1]]
    true_range = np.maximum(
        high - low,
        np.maximum(np.abs(high - previous_close), np.abs(low - previous_close)),
    )
    cumulative = np.r_[0.0, np.cumsum(true_range, dtype=np.float64)]
    result = np.full(len(close), np.nan, dtype=np.float64)
    if len(close) >= period:
        result[period - 1 :] = (
            cumulative[period:] - cumulative[:-period]
        ) / period
    return result


def _is_confirmed_break(
    values: npt.NDArray[np.float64],
    index: int,
    level: float,
    direction: Direction,
    config: MarketStructureConfig,
    atr: npt.NDArray[np.float64],
    gap_before: npt.NDArray[np.bool_],
) -> bool:
    start = index - config.confirmation_bars + 1
    if start < 0 or gap_before[start + 1 : index + 1].any():
        return False

    observed = values[start : index + 1]
    if config.break_buffer_atr == 0:
        buffer = np.zeros(len(observed), dtype=np.float64)
    else:
        observed_atr = atr[start : index + 1]
        if not np.isfinite(observed_atr).all():
            return False
        buffer = config.break_buffer_atr * observed_atr

    if direction == "bullish":
        return bool(np.all(observed > (level + buffer)))
    return bool(np.all(observed < (level - buffer)))


def detect_market_structure(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    config: MarketStructureConfig | StructureDefinition | None = None,
    *,
    timestamps: Sequence[datetime] | None = None,
) -> MarketStructureResult:
    """Detect causal structure events from completed M1 bars and UTC timestamps.

    Every timestamp must be timezone-aware UTC, unique, increasing, and minute
    aligned. Any interval other than exactly 60 seconds is a gap. Swing windows
    cannot cross gaps; multi-bar break confirmation restarts after a gap, while
    already-confirmed levels and trend state persist. A one-bar break may be
    confirmed on the first bar after a gap. Ambiguous double-wick bars consume
    neither active level and do not advance trend state.

    The detector emits structure events only. It does not generate trade advice,
    simulate fills, or establish predictive edge.
    """
    if config is None:
        cfg = MarketStructureConfig()
        definition = cfg.to_definition()
    elif isinstance(config, StructureDefinition):
        definition = config
        cfg = MarketStructureConfig(
            swing_window=definition.swing_window,
            break_basis=definition.break_basis,
            confirmation_bars=definition.confirmation_bars,
            break_buffer_atr=definition.break_buffer_atr,
            atr_period=definition.atr_period,
        )
    else:
        cfg = config
        definition = cfg.to_definition()

    high_array, low_array, close_array = _validate_ohlc(high, low, close)
    count = len(close_array)
    gap_before = _validate_utc_timestamps(timestamps, count)
    atr = _atr(high_array, low_array, close_array, cfg.atr_period)

    if cfg.break_basis == "wick":
        up_values = high_array
        down_values = low_array
    else:
        up_values = close_array
        down_values = close_array

    swings: list[SwingPoint] = []
    breaks: list[StructureBreak] = []
    ambiguous: list[int] = []

    active_high: SwingPoint | None = None
    active_low: SwingPoint | None = None
    high_consumed = False
    low_consumed = False
    trend = 0

    for index in range(count):
        bullish_break = (
            active_high is not None
            and not high_consumed
            and _is_confirmed_break(
                up_values, index, active_high.price, "bullish", cfg, atr, gap_before
            )
        )
        bearish_break = (
            active_low is not None
            and not low_consumed
            and _is_confirmed_break(
                down_values, index, active_low.price, "bearish", cfg, atr, gap_before
            )
        )

        if bullish_break and bearish_break:
            # OHLC cannot reveal which side traded first. Keep both active
            # levels available; this bar is ambiguous, not a confirmed break.
            ambiguous.append(index)
        elif bullish_break and active_high is not None:
            kind: StructureKind = "CHOCH" if trend == -1 else "BOS"
            breaks.append(
                StructureBreak(
                    kind=kind,
                    direction="bullish",
                    level=active_high.price,
                    pivot_index=active_high.pivot_index,
                    pivot_confirmed_index=active_high.confirmed_index,
                    break_index=index,
                    break_price=float(up_values[index]),
                    variant_id=cfg.variant_id,
                    definition_id=definition.definition_id,
                )
            )
            trend = 1
            high_consumed = True
        elif bearish_break and active_low is not None:
            kind = "CHOCH" if trend == 1 else "BOS"
            breaks.append(
                StructureBreak(
                    kind=kind,
                    direction="bearish",
                    level=active_low.price,
                    pivot_index=active_low.pivot_index,
                    pivot_confirmed_index=active_low.confirmed_index,
                    break_index=index,
                    break_price=float(down_values[index]),
                    variant_id=cfg.variant_id,
                    definition_id=definition.definition_id,
                )
            )
            trend = -1
            low_consumed = True

        # Confirm the pivot only after processing this bar's breaks. Therefore
        # a newly confirmed pivot cannot be treated as known earlier in time.
        candidate = index - cfg.swing_window
        left = candidate - cfg.swing_window
        if left >= 0 and not gap_before[left + 1 : index + 1].any():
            right_slice = slice(candidate + 1, index + 1)
            left_slice = slice(left, candidate)

            is_swing_high = bool(
                high_array[candidate] > np.max(high_array[left_slice])
                and high_array[candidate] > np.max(high_array[right_slice])
            )
            is_swing_low = bool(
                low_array[candidate] < np.min(low_array[left_slice])
                and low_array[candidate] < np.min(low_array[right_slice])
            )

            if is_swing_high:
                point = SwingPoint(
                    "swing_high",
                    candidate,
                    index,
                    float(high_array[candidate]),
                )
                swings.append(point)
                active_high = point
                high_consumed = False

            if is_swing_low:
                point = SwingPoint(
                    "swing_low",
                    candidate,
                    index,
                    float(low_array[candidate]),
                )
                swings.append(point)
                active_low = point
                low_consumed = False

    trend_label: Literal["unknown", "bullish", "bearish"] = (
        "bullish" if trend == 1 else "bearish" if trend == -1 else "unknown"
    )
    return MarketStructureResult(
        variant_id=cfg.variant_id,
        definition_id=definition.definition_id,
        rows=count,
        swings=tuple(swings),
        breaks=tuple(breaks),
        ambiguous_break_indices=tuple(ambiguous),
        gap_indices=tuple(int(item) for item in np.flatnonzero(gap_before)),
        final_trend=trend_label,
    )


def run_market_structure_variants(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    configs: Sequence[MarketStructureConfig | StructureDefinition] | None = None,
    *,
    timestamps: Sequence[datetime] | None = None,
) -> dict[str, MarketStructureResult]:
    """Run definitions; output is events only, never backtest P&L."""
    selected = tuple(configs) if configs is not None else market_structure_variants()
    if not selected:
        raise ValueError("at least one market-structure config is required")
    identifiers = [
        item.variant_key if isinstance(item, StructureDefinition) else item.variant_id
        for item in selected
    ]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("market-structure variant IDs must be unique")
    return {
        identifier: detect_market_structure(
            high, low, close, item, timestamps=timestamps
        )
        for identifier, item in zip(identifiers, selected, strict=True)
    }
