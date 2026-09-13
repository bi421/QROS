"""Deterministic daily XAUUSD + macro observation assembly for Phase 5.2.

This module is the boundary between the canonical XAUUSD research source and
the research dataset. It accepts either the canonical MT5 M1 source or the
canonical D1 artifact deterministically produced from that MT5 M1 source.

* XAUUSD M1 bars are aggregated by UTC calendar day when an M1 source is used.
* Canonical D1 rows are accepted without re-aggregation.
* Daily OHLC uses first-open, max-high, min-low, last-close.
* Tick and real volume are summed; spread is averaged when present.
* Macro sources contribute only observations that actually exist on the
  same UTC calendar day. No interpolation or forward-fill is performed.
* The returned observations are ordered by UTC day and carry source counts.

No labels or model features are created here. That separation prevents the
calendar/alignment boundary from being silently mixed with feature warm-up
or future-label eligibility.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class DailyXAUBar:
    day: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    tick_volume: float
    spread: float | None
    real_volume: float
    m1_rows: int
    vwap: float | None = None


@dataclass(frozen=True)
class DailyMacroObservation:
    day: str
    dxy: float
    us10y: float
    vix: float


@dataclass(frozen=True)
class DailyObservation:
    day: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    tick_volume: float
    spread: float | None
    real_volume: float
    dxy: float
    us10y: float
    vix: float
    m1_rows: int
    vwap: float | None = None


def _utc_iso(value: str) -> str:
    value = value.strip()
    if value.isdigit():
        n = int(value)
        if abs(n) >= 100_000_000_000:
            dt = datetime.fromtimestamp(n / 1000, tz=timezone.utc)
        elif abs(n) >= 1_000_000_000:
            dt = datetime.fromtimestamp(n, tz=timezone.utc)
        else:
            raise ValueError(f"unsupported numeric timestamp: {value}")
        return dt.isoformat().replace("+00:00", "Z")
    if value.endswith("Z"):
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    else:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _day(timestamp: str) -> str:
    return timestamp[:10]


def _float(row: dict[str, str | None], key: str) -> float:
    value = row.get(key)
    if value is None or value.strip() == "":
        raise ValueError(f"missing numeric field: {key}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite numeric field: {key}")
    return number


def _load_daily_xau_from_d1(path: str | Path) -> tuple[DailyXAUBar, ...]:
    """Load the canonical D1 artifact produced from the MT5 M1 source.

    The repository's D1 preparation script publishes Date/Time/OHLC/tick_volume
    from real MT5 M1 data. No synthetic rows or repair are introduced here.
    """
    path = Path(path)
    output: list[DailyXAUBar] = []
    seen_days: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = {str(x).strip().lower(): x for x in (reader.fieldnames or [])}
        required = {"date", "time", "open", "high", "low", "close", "tick_volume"}
        if not required.issubset(fields):
            raise ValueError("XAUUSD D1 source must use canonical Date/Time/OHLCV schema")
        for raw in reader:
            row = {str(k).strip().lower(): v for k, v in raw.items() if k is not None}
            date_value = str(row["date"]).strip()
            time_value = str(row["time"]).strip()
            ts = _utc_iso(f"{date_value}T{time_value}Z")
            day = _day(ts)
            if day in seen_days:
                raise ValueError(f"XAUUSD duplicate calendar day: {day}")
            seen_days.add(day)
            open_ = _float(row, "open")
            high = _float(row, "high")
            low = _float(row, "low")
            close = _float(row, "close")
            tick_volume = _float(row, "tick_volume")
            if high < max(open_, close) or low > min(open_, close) or high < low:
                raise ValueError(f"invalid OHLC relationship at calendar day: {day}")
            output.append(
                DailyXAUBar(
                    day=day,
                    timestamp=f"{day}T00:00:00Z",
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    tick_volume=tick_volume,
                    spread=None,
                    real_volume=0.0,
                    m1_rows=0,
                    vwap=(high + low + close) / 3.0,
                )
            )
    return tuple(sorted(output, key=lambda x: x.day))


def load_daily_xau_from_m1(path: str | Path) -> tuple[DailyXAUBar, ...]:
    """Load canonical XAUUSD research data into UTC daily OHLCV bars.

    Canonical MT5 M1 CSV is aggregated deterministically. The canonical D1
    artifact generated from that same MT5 M1 source is also accepted because
    the existing production research dataset uses that derived artifact.
    """
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = {str(x).strip().lower() for x in (reader.fieldnames or [])}

    m1_required = {"time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"}
    d1_required = {"date", "time", "open", "high", "low", "close", "tick_volume"}
    if d1_required.issubset(fields) and not m1_required.issubset(fields):
        return _load_daily_xau_from_d1(path)
    if not m1_required.issubset(fields):
        raise ValueError("XAUUSD source must use canonical MT5 M1 or canonical D1 OHLCV schema")

    groups: dict[str, list[tuple[str, float, float, float, float, float, float | None, float]]] = {}
    seen_timestamps: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            row = {str(k).strip().lower(): v for k, v in raw.items() if k is not None}
            ts = _utc_iso(str(row["time"]))
            if ts in seen_timestamps:
                raise ValueError(f"XAUUSD duplicate timestamp: {ts}")
            seen_timestamps.add(ts)
            open_ = _float(row, "open")
            high = _float(row, "high")
            low = _float(row, "low")
            close = _float(row, "close")
            if high < max(open_, close) or low > min(open_, close) or high < low:
                raise ValueError(f"invalid OHLC relationship at timestamp: {ts}")
            values = (
                ts,
                open_,
                high,
                low,
                close,
                _float(row, "tick_volume"),
                _float(row, "spread"),
                _float(row, "real_volume"),
            )
            groups.setdefault(_day(ts), []).append(values)

    output: list[DailyXAUBar] = []
    for day in sorted(groups):
        rows = sorted(groups[day], key=lambda x: x[0])
        spreads = [r[6] for r in rows]
        output.append(
            DailyXAUBar(
                day=day,
                timestamp=f"{day}T00:00:00Z",
                open=rows[0][1],
                high=max(r[2] for r in rows),
                low=min(r[3] for r in rows),
                close=rows[-1][4],
                tick_volume=sum(r[5] for r in rows),
                spread=sum(spreads) / len(spreads) if spreads else None,
                real_volume=sum(r[7] for r in rows),
                m1_rows=len(rows),
                vwap=(
                    sum(((r[2] + r[3] + r[4]) / 3.0) * r[5] for r in rows) / sum(r[5] for r in rows)
                    if sum(r[5] for r in rows) != 0
                    else ((rows[-1][2] + rows[-1][3] + rows[-1][4]) / 3.0)
                ),
            )
        )
    return tuple(output)


def load_dxy_daily(path: str | Path) -> dict[str, float]:
    """Load DXY daily close observations keyed by UTC calendar day."""
    path = Path(path)
    out: dict[str, float] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = {str(x).strip().lower() for x in (reader.fieldnames or [])}
        required = {"timestamp", "close"}
        if not required.issubset(fields):
            raise ValueError("DXY source must contain timestamp and close columns")
        for raw in reader:
            row = {str(k).strip().lower(): v for k, v in raw.items() if k is not None}
            ts = _utc_iso(str(row["timestamp"]))
            day = _day(ts)
            if day in out:
                raise ValueError(f"DXY duplicate calendar day: {day}")
            out[day] = _float(row, "close")
    return out


def _load_fred_daily(path: str | Path, value_key: str, symbol: str) -> dict[str, float]:
    path = Path(path)
    out: dict[str, float] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = {str(x).strip().lower() for x in (reader.fieldnames or [])}
        required = {"observation_date", value_key}
        if not required.issubset(fields):
            raise ValueError(
                f"{symbol} source must contain observation_date and {value_key} columns"
            )
        for raw in reader:
            row = {str(k).strip().lower(): v for k, v in raw.items() if k is not None}
            raw_value = row.get(value_key)
            if raw_value is None or raw_value.strip() in {"", "."}:
                continue
            ts = _utc_iso(str(row["observation_date"]))
            day = _day(ts)
            if day in out:
                raise ValueError(f"{symbol} duplicate calendar day: {day}")
            out[day] = _float(row, value_key)
    return out


def load_macro_daily(
    dxy_path: str | Path,
    us10y_path: str | Path,
    vix_path: str | Path,
) -> tuple[DailyMacroObservation, ...]:
    """Return the exact four-way macro daily intersection as immutable observations."""
    dxy = load_dxy_daily(dxy_path)
    us10y = _load_fred_daily(us10y_path, "dgs10", "US10Y")
    vix = _load_fred_daily(vix_path, "vixcls", "VIX")
    common = sorted(set(dxy) & set(us10y) & set(vix))
    return tuple(DailyMacroObservation(day, dxy[day], us10y[day], vix[day]) for day in common)


def build_daily_common_dataset(
    xau_path: str | Path,
    dxy_path: str | Path,
    us10y_path: str | Path,
    vix_path: str | Path,
) -> tuple[DailyObservation, ...]:
    """Build the exact common-day dataset from canonical XAU and macro sources."""
    xau = {bar.day: bar for bar in load_daily_xau_from_m1(xau_path)}
    macro = load_macro_daily(dxy_path, us10y_path, vix_path)
    observations: list[DailyObservation] = []
    for m in macro:
        bar = xau.get(m.day)
        if bar is None:
            continue
        observations.append(
            DailyObservation(
                day=bar.day,
                timestamp=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                tick_volume=bar.tick_volume,
                spread=bar.spread,
                real_volume=bar.real_volume,
                dxy=m.dxy,
                us10y=m.us10y,
                vix=m.vix,
                m1_rows=bar.m1_rows,
                vwap=bar.vwap,
            )
        )
    return tuple(observations)


__all__ = [
    "DailyXAUBar",
    "DailyMacroObservation",
    "DailyObservation",
    "load_daily_xau_from_m1",
    "load_dxy_daily",
    "load_macro_daily",
    "build_daily_common_dataset",
]
