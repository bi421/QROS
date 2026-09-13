"""Deterministic daily XAUUSD + macro observation assembly for Phase 5.2.

The canonical XAUUSD sources are either real MT5 M1 data or the canonical D1
artifact derived from that M1 data. Both paths must expose the same VWAP
semantic: tick-volume-weighted daily typical price. A D1 OHLC row does not
contain enough information to reconstruct VWAP, so canonical D1 input must
carry the precomputed VWAP explicitly. This module never substitutes
(high + low + close) / 3 for a missing VWAP.
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
    """Load the canonical D1 artifact with its precomputed true VWAP.

    The D1 preparation pipeline derives each row from the source M1 bars and
    therefore publishes the tick-volume-weighted VWAP. Rejecting a D1 file
    without that field is intentional: falling back to typical price would
    silently change feature semantics at an M1/D1 source boundary.
    """
    path = Path(path)
    output: list[DailyXAUBar] = []
    seen_days: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = {str(x).strip().lower(): x for x in (reader.fieldnames or [])}
        required = {
            "date",
            "time",
            "open",
            "high",
            "low",
            "close",
            "tick_volume",
            "vwap",
        }
        if not required.issubset(fields):
            raise ValueError(
                "XAUUSD canonical D1 source must contain Date/Time/OHLC/tick_volume/vwap schema"
            )
        for raw in reader:
            row = {str(k).strip().lower(): v for k, v in raw.items() if k is not None}
            date_value = str(row["date"]).strip()
            time_value = str(row["time"]).strip()
            normalized_date = (
                date_value.replace(".", "-") if date_value.count(".") == 2 else date_value
            )
            ts = _utc_iso(f"{normalized_date}T{time_value}Z")
            day = _day(ts)
            if day in seen_days:
                raise ValueError(f"XAUUSD duplicate calendar day: {day}")
            seen_days.add(day)
            open_ = _float(row, "open")
            high = _float(row, "high")
            low = _float(row, "low")
            close = _float(row, "close")
            tick_volume = _float(row, "tick_volume")
            vwap = _float(row, "vwap")
            if high < max(open_, close) or low > min(open_, close) or high < low:
                raise ValueError(f"invalid OHLC relationship at calendar day: {day}")
            if not low <= vwap <= high:
                raise ValueError(f"invalid VWAP range at calendar day: {day}")
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
                    vwap=vwap,
                )
            )
    return tuple(sorted(output, key=lambda x: x.day))


def load_daily_xau_from_m1(path: str | Path) -> tuple[DailyXAUBar, ...]:
    """Load canonical XAUUSD data into deterministic UTC daily OHLCV bars.

    M1 input computes true daily VWAP from every M1 typical price weighted by
    tick volume. Canonical D1 input must carry the same precomputed semantic.
    """
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = {str(x).strip().lower() for x in (reader.fieldnames or [])}

    m1_required = {
        "time",
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "spread",
        "real_volume",
    }
    d1_required = {
        "date",
        "time",
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "vwap",
    }
    if d1_required.issubset(fields) and not m1_required.issubset(fields):
        return _load_daily_xau_from_d1(path)
    if not m1_required.issubset(fields):
        raise ValueError(
            "XAUUSD source must use canonical MT5 M1 or canonical D1 "
            "OHLCV+VWAP schema"
        )

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
            groups.setdefault(_day(ts), []).append(
                (
                    ts,
                    open_,
                    high,
                    low,
                    close,
                    _float(row, "tick_volume"),
                    _float(row, "spread"),
                    _float(row, "real_volume"),
                )
            )

    output: list[DailyXAUBar] = []
    for day in sorted(groups):
        rows = sorted(groups[day], key=lambda x: x[0])
        spreads = [r[6] for r in rows]
        volume_sum = sum(r[5] for r in rows)
        vwap = (
            sum(((r[2] + r[3] + r[4]) / 3.0) * r[5] for r in rows) / volume_sum
            if volume_sum != 0
            else ((rows[-1][2] + rows[-1][3] + rows[-1][4]) / 3.0)
        )
        output.append(
            DailyXAUBar(
                day=day,
                timestamp=f"{day}T00:00:00Z",
                open=rows[0][1],
                high=max(r[2] for r in rows),
                low=min(r[3] for r in rows),
                close=rows[-1][4],
                tick_volume=volume_sum,
                spread=sum(spreads) / len(spreads) if spreads else None,
                real_volume=sum(r[7] for r in rows),
                m1_rows=len(rows),
                vwap=vwap,
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
        if not {"timestamp", "close"}.issubset(fields):
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
        if not {"observation_date", value_key}.issubset(fields):
            raise ValueError(f"{symbol} source must contain observation_date and {value_key} columns")
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
    """Return the exact four-way macro daily intersection."""
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
