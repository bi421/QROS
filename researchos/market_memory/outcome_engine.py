"""Outcome Engine — deterministic forward outcome calculation for market events.

Forward horizons are calendar days and resolved to the first actual observation
at or after the target timestamp. Threshold labels, MFE and MAE are explicitly
directional so bullish and bearish events use the same contract from opposite
market perspectives.
"""
from __future__ import annotations

from bisect import bisect_left
from datetime import datetime, timedelta
import math

import polars as pl

from researchos.market_memory.event_schema import EventOutcome, MarketEvent


def _timeframe_minutes(timeframe: str) -> int:
    aliases = {
        "m1": 1, "1m": 1, "m5": 5, "5m": 5, "m15": 15, "15m": 15,
        "m30": 30, "30m": 30, "h1": 60, "1h": 60, "h4": 240, "4h": 240,
        "d1": 1440, "1d": 1440, "w1": 10080, "1w": 10080,
    }
    normalized = timeframe.strip().lower()
    if normalized not in aliases:
        raise ValueError(f"Unsupported timeframe for forward outcome calculation: {timeframe}")
    return aliases[normalized]


def _directional_return(event: MarketEvent, raw_return: float) -> float:
    direction = event.direction.strip().lower()
    if direction in {"bullish", "long", "up"}:
        return raw_return
    if direction in {"bearish", "short", "down"}:
        return -raw_return
    raise ValueError(f"Unsupported event direction for outcome calculation: {event.direction}")


def compute_forward_outcomes(
    events: list[MarketEvent],
    price_df: pl.DataFrame,
    horizons: list[int] | None = None,
    threshold: float = 0.0,
) -> list[MarketEvent]:
    """Compute leakage-safe calendar-day outcomes from actual future observations."""
    if horizons is None:
        horizons = [1, 2, 3, 5, 10, 20]
    if not horizons or any(
        not isinstance(h, int) or isinstance(h, bool) or h < 1 for h in horizons
    ):
        raise ValueError("horizons must be a non-empty list of positive integers")
    if len(set(horizons)) != len(horizons):
        raise ValueError("horizons must not contain duplicates")
    if not math.isfinite(threshold) or threshold < 0:
        raise ValueError("threshold must be finite and non-negative")
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required.difference(price_df.columns)
    if missing:
        raise ValueError(f"price_df missing columns: {sorted(missing)}")
    if len(price_df) == 0:
        return events

    frame = price_df.sort("timestamp")
    timestamps = frame["timestamp"].to_list()
    if any(not isinstance(ts, datetime) for ts in timestamps):
        raise ValueError("price timestamps must be datetimes")
    if any(current <= previous for previous, current in zip(timestamps, timestamps[1:])):
        raise ValueError("price timestamps must be unique and strictly increasing")
    timezone = timestamps[0].tzinfo if timestamps else None
    if any(ts.tzinfo != timezone for ts in timestamps):
        raise ValueError("price timestamps must use a consistent timezone")
    for event in events:
        if event.timestamp.tzinfo != timezone:
            raise ValueError("event and price timestamps must use the same timezone")
        if not math.isfinite(event.event_price) or event.event_price == 0:
            raise ValueError("event price must be finite and non-zero for percentage returns")
    for column in ("open", "high", "low", "close"):
        values = frame[column].to_list()
        if any(value is None or not math.isfinite(float(value)) for value in values):
            raise ValueError(f"{column} prices must all be finite and non-null")
    closes = frame["close"].to_list()
    highs = frame["high"].to_list()
    lows = frame["low"].to_list()
    ts_to_idx = {ts: i for i, ts in enumerate(timestamps)}

    updated_events: list[MarketEvent] = []
    for event in events:
        if event.timestamp not in ts_to_idx:
            updated_events.append(event)
            continue
        idx = ts_to_idx[event.timestamp]
        _timeframe_minutes(event.timeframe)
        event_close = event.event_price
        returns: dict[str, float | None] = {}
        directions: dict[str, str | None] = {}
        mfe: dict[str, float | None] = {}
        mae: dict[str, float | None] = {}
        hits: dict[str, bool | None] = {}
        realized_ends: dict[str, str] = {}

        for h in horizons:
            target = event.timestamp + timedelta(days=h)
            future_idx = bisect_left(timestamps, target, lo=idx + 1)
            if future_idx >= len(timestamps):
                returns[f"return_{h}d"] = None
                directions[f"direction_{h}d"] = None
                mfe[f"mfe_{h}d"] = None
                mae[f"mae_{h}d"] = None
                hits[f"hit_{h}d"] = None
                continue

            realized_end = timestamps[future_idx]
            realized_ends[f"realized_end_{h}d"] = realized_end.isoformat()
            future_close = closes[future_idx]
            window_high = max(highs[idx + 1 : future_idx + 1])
            window_low = min(lows[idx + 1 : future_idx + 1])

            ret = (future_close - event_close) / event_close
            directional_ret = _directional_return(event, ret)
            if event.direction.strip().lower() in {"bullish", "long", "up"}:
                favorable_excursion = (window_high - event_close) / event_close
                adverse_excursion = (window_low - event_close) / event_close
            else:
                favorable_excursion = (event_close - window_low) / event_close
                adverse_excursion = (event_close - window_high) / event_close

            returns[f"return_{h}d"] = ret
            directions[f"direction_{h}d"] = "up" if ret > 0 else "down" if ret < 0 else "flat"
            mfe[f"mfe_{h}d"] = favorable_excursion
            mae[f"mae_{h}d"] = adverse_excursion
            hits[f"hit_{h}d"] = directional_ret > threshold

        outcome = EventOutcome(
            event_id=event.event_id,
            asset=event.asset,
            timeframe=event.timeframe,
            event_timestamp=event.timestamp,
            return_1d=returns.get("return_1d"),
            return_2d=returns.get("return_2d"),
            return_3d=returns.get("return_3d"),
            return_5d=returns.get("return_5d"),
            return_10d=returns.get("return_10d"),
            return_20d=returns.get("return_20d"),
            direction_1d=directions.get("direction_1d"),
            direction_2d=directions.get("direction_2d"),
            direction_3d=directions.get("direction_3d"),
            direction_5d=directions.get("direction_5d"),
            direction_10d=directions.get("direction_10d"),
            direction_20d=directions.get("direction_20d"),
            mfe_1d=mfe.get("mfe_1d"),
            mae_1d=mae.get("mae_1d"),
            mfe_5d=mfe.get("mfe_5d"),
            mae_5d=mae.get("mae_5d"),
            mfe_20d=mfe.get("mfe_20d"),
            mae_20d=mae.get("mae_20d"),
            hit_threshold_1d=hits.get("hit_1d"),
            hit_threshold_5d=hits.get("hit_5d"),
            hit_threshold_20d=hits.get("hit_20d"),
            outcome_calculation_method="direction_aware_forward_return_from_actual_future_observation_timestamp",
            data_availability={
                f"return_{h}d": "available" if returns.get(f"return_{h}d") is not None else "unavailable"
                for h in horizons
            } | realized_ends,
        )
        updated_events.append(
            MarketEvent(
                event_id=event.event_id,
                asset=event.asset,
                timeframe=event.timeframe,
                event_type=event.event_type,
                direction=event.direction,
                timestamp=event.timestamp,
                event_price=event.event_price,
                context=event.context,
                outcome=outcome,
                dataset_source=event.dataset_source,
                computation_method=event.computation_method,
                seed=event.seed,
            )
        )
    return updated_events
