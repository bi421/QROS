"""Audit Phase 5.2 exact-timestamp versus calendar-date macro overlap.

This is a read-only diagnostic. It does not alter Phase 5.2 execution semantics,
which currently require exact timestamp equality across XAUUSD and all macro
series. Its purpose is to distinguish genuine date coverage loss from
timestamp-of-day mismatch before any execution change is considered.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from researchos.experiments.phase52.scripts.run_phase52_experiment import (
    _load_candles,
    _load_macro_series,
)


def _date_key(value: object) -> str:
    return str(value)[:10]


def _time_key(value: object) -> str:
    text = str(value)
    if "T" in text:
        text = text.split("T", 1)[1]
    elif " " in text:
        text = text.split(" ", 1)[1]
    return text[:8]


def _unique(values: Iterable[object]) -> list[object]:
    return list(dict.fromkeys(values))


def audit_overlap(
    price_timestamps: Iterable[object],
    macro_timestamps: dict[str, Iterable[object]],
) -> dict[str, object]:
    """Return exact and calendar-date overlap diagnostics without repairing data."""
    price = _unique(price_timestamps)
    macro = {name: _unique(values) for name, values in macro_timestamps.items()}

    exact_sets = {name: set(values) for name, values in macro.items()}
    exact_common = [value for value in price if all(value in exact_sets[name] for name in macro)]
    date_sets = {
        name: {_date_key(value) for value in values}
        for name, values in macro.items()
    }
    price_dates = {_date_key(value) for value in price}
    date_common = sorted(
        price_dates.intersection(*(date_sets[name] for name in macro))
    )

    return {
        "price_rows": len(price),
        "macro_rows": {name: len(values) for name, values in macro.items()},
        "exact_timestamp_common": len(exact_common),
        "exact_timestamp_first": _date_key(exact_common[0]) if exact_common else None,
        "exact_timestamp_last": _date_key(exact_common[-1]) if exact_common else None,
        "calendar_date_common": len(date_common),
        "calendar_date_first": date_common[0] if date_common else None,
        "calendar_date_last": date_common[-1] if date_common else None,
        "exact_timestamp_time_of_day": dict(
            Counter(_time_key(value) for value in exact_common)
        ),
        "price_time_of_day": dict(Counter(_time_key(value) for value in price)),
        "macro_time_of_day": {
            name: dict(Counter(_time_key(value) for value in values))
            for name, values in macro.items()
        },
        "date_only_gap_vs_exact": len(date_common) - len(exact_common),
        "diagnostic_boundary": (
            "Calendar-date overlap is diagnostic only. Phase 5.2 execution "
            "still requires exact timestamp equality; no date normalization, "
            "forward-fill, interpolation, resampling, or synthetic repair "
            "is performed by this audit."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Phase 5.2 timestamp/calendar overlap")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--dxy", required=True)
    parser.add_argument("--us10y", required=True)
    parser.add_argument("--vix", required=True)
    parser.add_argument("--format", default="auto", choices=["mt5", "tradingview", "auto"])
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    close, high, low, volume, price_timestamps = _load_candles(
        args.csv, args.format, args.symbol, args.timeframe
    )
    del close, high, low, volume

    macro_timestamps: dict[str, list[object]] = {}
    for name, path in (
        ("DXY", args.dxy),
        ("US10Y", args.us10y),
        ("VIX", args.vix),
    ):
        values, timestamps = _load_macro_series(
            path, args.format, name, args.timeframe
        )
        del values
        macro_timestamps[name] = timestamps

    report = audit_overlap(price_timestamps, macro_timestamps)
    text = json.dumps(report, indent=2, sort_keys=True, default=str)

    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
