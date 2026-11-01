"""Strict, read-only adapter from tabular M1 bars to market-structure inputs.

The adapter validates and preserves caller order. It never sorts, fills gaps,
localizes timestamps, reads files, fetches market data, or invokes the detector.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype


@dataclass(frozen=True, slots=True)
class MarketStructureInput:
    """Immutable M1 input contract; optional MT5 fields retain source units."""

    symbol: str
    timeframe: Literal["M1"]
    timestamps: tuple[datetime, ...]
    open: tuple[float, ...]
    high: tuple[float, ...]
    low: tuple[float, ...]
    close: tuple[float, ...]
    spread_points: tuple[float | None, ...]
    tick_volume: tuple[float | None, ...]
    real_volume: tuple[float | None, ...]

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol.strip() != self.symbol:
            raise ValueError("symbol must be a non-empty, trimmed string")
        if self.timeframe != "M1":
            raise ValueError("market-structure V1 accepts M1 only")
        lengths = {
            len(self.timestamps), len(self.open), len(self.high), len(self.low),
            len(self.close), len(self.spread_points), len(self.tick_volume),
            len(self.real_volume),
        }
        if len(lengths) != 1 or not self.timestamps:
            raise ValueError("all input fields must have the same non-zero length")

    @property
    def row_count(self) -> int:
        return len(self.close)


def _numeric_column(frame: pd.DataFrame, name: str) -> np.ndarray:
    series = frame[name]
    if not is_numeric_dtype(series.dtype) or is_bool_dtype(series.dtype):
        raise TypeError(f"{name} must have a numeric dtype")
    values = series.to_numpy(dtype=np.float64, copy=True)
    if not np.isfinite(values).all():
        raise ValueError(f"{name} contains missing or non-finite values")
    return values


def _optional_numeric_column(
    frame: pd.DataFrame,
    name: str,
    row_count: int,
) -> tuple[float | None, ...]:
    if name not in frame.columns:
        return (None,) * row_count
    series = frame[name]
    if not is_numeric_dtype(series.dtype) or is_bool_dtype(series.dtype):
        raise TypeError(f"{name} must have a numeric dtype")
    result: list[float | None] = []
    for index, value in enumerate(series.tolist()):
        if pd.isna(value):
            result.append(None)
            continue
        number = float(value)
        if not np.isfinite(number) or number < 0:
            raise ValueError(f"{name} must be finite and non-negative at index {index}")
        result.append(number)
    return tuple(result)


def market_structure_input_from_frame(
    frame: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str = "M1",
    timestamp_column: str = "time",
) -> MarketStructureInput:
    """Validate a pre-loaded frame without mutating, sorting, or repairing it.

    Required columns: UTC datetime `time` (or `timestamp_column`), open, high,
    low, close. Optional MT5 fields: spread (points), tick_volume, real_volume.
    String timestamps and naive/non-UTC timestamps are rejected rather than
    guessed or silently localized. Gaps are preserved as-is for the detector.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    if not isinstance(symbol, str) or not symbol or symbol.strip() != symbol:
        raise ValueError("symbol must be a non-empty, trimmed string")
    if timeframe != "M1":
        raise ValueError("market-structure V1 accepts M1 only")
    if not isinstance(timestamp_column, str) or not timestamp_column:
        raise ValueError("timestamp_column must be a non-empty string")
    if frame.empty:
        raise ValueError("input frame must contain at least one row")
    if not frame.columns.is_unique:
        raise ValueError("input frame contains duplicate column names")

    required = (timestamp_column, "open", "high", "low", "close")
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    if "is_complete" in frame.columns and not frame["is_complete"].map(
        lambda value: isinstance(value, (bool, np.bool_)) and bool(value)
    ).all():
        raise ValueError("all input bars must be explicitly complete")

    timestamps: list[datetime] = []
    previous_epoch: int | None = None
    for index, value in enumerate(frame[timestamp_column].tolist()):
        if not isinstance(value, datetime):
            raise TypeError(f"{timestamp_column} must contain datetime values; index {index}")
        if (
            value.tzinfo is None
            or value.utcoffset() != timedelta(0)
            or value.tzname() not in ("UTC", "Etc/UTC")
        ):
            raise ValueError(f"{timestamp_column} must be timezone-aware UTC; index {index}")
        if value.second != 0 or value.microsecond != 0:
            raise ValueError(f"{timestamp_column} must be aligned to whole minutes; index {index}")
        epoch = int(value.timestamp())
        if previous_epoch is not None and epoch <= previous_epoch:
            raise ValueError(f"{timestamp_column} must be unique and strictly increasing; index {index}")
        timestamps.append(value.to_pydatetime() if hasattr(value, "to_pydatetime") else value)
        previous_epoch = epoch

    open_values = _numeric_column(frame, "open")
    high_values = _numeric_column(frame, "high")
    low_values = _numeric_column(frame, "low")
    close_values = _numeric_column(frame, "close")
    if np.any(high_values < low_values):
        raise ValueError("high must be >= low")
    if (
        np.any(high_values < open_values)
        or np.any(high_values < close_values)
        or np.any(low_values > open_values)
        or np.any(low_values > close_values)
    ):
        raise ValueError("open and close must lie within each bar's high/low range")

    count = len(frame)
    return MarketStructureInput(
        symbol=symbol,
        timeframe="M1",
        timestamps=tuple(timestamps),
        open=tuple(float(value) for value in open_values),
        high=tuple(float(value) for value in high_values),
        low=tuple(float(value) for value in low_values),
        close=tuple(float(value) for value in close_values),
        spread_points=_optional_numeric_column(frame, "spread", count),
        tick_volume=_optional_numeric_column(frame, "tick_volume", count),
        real_volume=_optional_numeric_column(frame, "real_volume", count),
    )
