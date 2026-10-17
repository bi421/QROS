"""Explain the final FastThreeState decision without changing the production CLI."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--close-column", default="close")
    parser.add_argument("--lookback", type=int, default=32)
    parser.add_argument("--efficiency-threshold", type=float, default=0.35)
    parser.add_argument("--min-move-bps", type=float, default=5.0)
    parser.add_argument("--date-column", default="Date")
    args = parser.parse_args()
    if args.lookback < 2:
        parser.error("--lookback must be >= 2")

    with args.csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV has no header")
        columns = {name.strip().lower(): name for name in reader.fieldnames}
        close_key = columns.get(args.close_column.strip().lower())
        date_key = columns.get(args.date_column.strip().lower())
        if close_key is None:
            raise ValueError(f"CSV missing close column: {args.close_column}")
        closes: list[float] = []
        dates: list[str] = []
        for row in reader:
            value = float(row[close_key])
            if not math.isfinite(value) or value <= 0:
                raise ValueError("CSV contains invalid close")
            closes.append(value)
            dates.append(row.get(date_key, "") if date_key else "")

    if not closes:
        raise ValueError("CSV contains no candles")
    window = closes[-args.lookback :]
    window_dates = dates[-args.lookback :]
    print(f"file={args.csv_path}")
    print(f"rows={len(closes)} lookback_requested={args.lookback} lookback_available={len(window)}")
    if window_dates and window_dates[0]:
        print(f"window_start={window_dates[0]} window_end={window_dates[-1]}")
    if len(window) < args.lookback:
        print("state=RANGE reason=warmup_insufficient")
        return 0

    first, last = window[0], window[-1]
    net = last - first
    path = sum(abs(window[i] - window[i - 1]) for i in range(1, len(window)))
    efficiency = abs(net) / path if path > 0 else 0.0
    move_bps = abs(net) / last * 10000.0
    if path <= 0:
        state, reason = "RANGE", "zero_path"
    elif efficiency < args.efficiency_threshold:
        state, reason = "RANGE", "efficiency_below_threshold"
    elif move_bps < args.min_move_bps:
        state, reason = "RANGE", "net_move_below_threshold"
    elif net > 0:
        state, reason = "UP", "directional_move_passed_thresholds"
    elif net < 0:
        state, reason = "DOWN", "directional_move_passed_thresholds"
    else:
        state, reason = "RANGE", "zero_net_move"

    print(f"first_close={first:.8f}")
    print(f"last_close={last:.8f}")
    print(f"net_move={net:.8f}")
    print(f"absolute_path={path:.8f}")
    print(f"directional_efficiency={efficiency:.8f} threshold={args.efficiency_threshold:.8f}")
    print(f"absolute_net_move_bps={move_bps:.8f} threshold={args.min_move_bps:.8f}")
    print(f"state={state} reason={reason}")
    print("note=close-only rolling trend proxy; not a validated trading edge or live market feed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
