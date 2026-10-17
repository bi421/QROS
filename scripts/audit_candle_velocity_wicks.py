"""Audit XAUUSD candle velocity and wick-conditioned forward outcomes."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import deque
from pathlib import Path

from researchos.orchestration.candle_velocity import CandleVelocityEngine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/curated/xauusd/xauusd_m1_2021_2025_mt5.csv")
    parser.add_argument(
        "--window", type=int, default=20, help="prior completed bars for velocity Z-score"
    )
    parser.add_argument("--z-threshold", type=float, default=2.0)
    parser.add_argument("--horizon", type=int, default=3, help="forward bars for endpoint outcome")
    parser.add_argument("--sideways-atr-fraction", type=float, default=0.25)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument(
        "--holdout-start",
        default="2025.01.01",
        help="event date starting the chronological holdout, YYYY.MM.DD",
    )
    parser.add_argument("--output", default="artifacts/candle_velocity_wick_audit.json")
    args = parser.parse_args()
    if args.window < 2 or args.horizon < 1 or args.sideways_atr_fraction < 0:
        parser.error("window >= 2, horizon >= 1, sideways-atr-fraction >= 0 required")
    source = Path(args.csv)
    engine = CandleVelocityEngine(window=args.window, z_threshold=args.z_threshold)
    ranges: deque[float] = deque(maxlen=args.window)
    pending: deque[dict[str, object]] = deque()
    counts: dict[str, dict[str, int]] = {}
    split_counts: dict[str, dict[str, dict[str, int]]] = {"TRAIN": {}, "HOLDOUT": {}}
    eligible = 0
    total_rows = 0
    first_timestamp = None
    last_timestamp = None
    previous_close = None
    with source.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"Open", "High", "Low", "Close"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV must contain columns {sorted(required)}")
        for row in reader:
            o, h, lo, c = (float(row[key]) for key in ("Open", "High", "Low", "Close"))
            if (
                not all(math.isfinite(v) and v > 0 for v in (o, h, lo, c))
                or h < max(o, c, lo)
                or lo > min(o, c, h)
            ):
                raise ValueError(f"invalid OHLC at CSV row {total_rows + 2}")
            timestamp = " ".join(part for part in (row.get("Date"), row.get("Time")) if part)
            if first_timestamp is None:
                first_timestamp = timestamp
            last_timestamp = timestamp
            total_rows += 1

            # Resolve signals only after their entire forward horizon is observed.
            while pending and int(pending[0]["index"]) + args.horizon <= total_rows - 1:
                event = pending.popleft()
                signed_move = int(event["direction"]) * (c - float(event["close"]))
                threshold = float(event["sideways_threshold"])
                outcome = (
                    "CONTINUATION"
                    if signed_move > threshold
                    else "REVERSAL"
                    if signed_move < -threshold
                    else "SIDEWAYS"
                )
                key = f"direction_{'UP' if int(event['direction']) == 1 else 'DOWN'}|{event['wick_pattern']}"
                group = counts.setdefault(
                    key, {name: 0 for name in ("CONTINUATION", "REVERSAL", "SIDEWAYS")}
                )
                group[outcome] += 1
                split = "HOLDOUT" if str(event["date"]) >= args.holdout_start else "TRAIN"
                split_group = split_counts[split].setdefault(
                    key, {name: 0 for name in ("CONTINUATION", "REVERSAL", "SIDEWAYS")}
                )
                split_group[outcome] += 1
                eligible += 1

            result = engine.update(o, h, lo, c, interval_seconds=args.interval_seconds)
            # A simple rolling mean true-range proxy, based only on completed prior bars.
            tr = (
                max(h - lo, abs(h - previous_close), abs(lo - previous_close))
                if previous_close is not None
                else h - lo
            )
            atr_proxy = sum(ranges) / len(ranges) if ranges else None
            if result["impulse"] and result["direction"] in (-1, 1) and atr_proxy is not None:
                pending.append(
                    {
                        "index": total_rows - 1,
                        "date": row.get("Date", ""),
                        "direction": result["direction"],
                        "close": c,
                        "sideways_threshold": args.sideways_atr_fraction * atr_proxy,
                        "wick_pattern": result["wick_pattern"],
                    }
                )
            ranges.append(tr)
            previous_close = c

    report = {}
    for key, group in sorted(counts.items()):
        n = sum(group.values())
        report[key] = {
            "n": n,
            "counts": group,
            "empirical_probabilities": {name: group[name] / n for name in group},
        }
    split_report = {}
    for split_name, split_groups in split_counts.items():
        split_report[split_name] = {}
        for key, group in sorted(split_groups.items()):
            n = sum(group.values())
            split_report[split_name][key] = {
                "n": n,
                "counts": group,
                "empirical_probabilities": {name: group[name] / n for name in group},
            }
    output = {
        "status": "COMPLETED_WITH_UNRESOLVED_TAIL_EXCLUDED" if pending else "COMPLETED",
        "source": str(source),
        "rows_read": total_rows,
        "first_timestamp_text": first_timestamp,
        "last_timestamp_text": last_timestamp,
        "specification": {
            "window": args.window,
            "z_threshold": args.z_threshold,
            "horizon_bars": args.horizon,
            "sideways_threshold": f"{args.sideways_atr_fraction} * prior rolling mean true range",
            "interval_seconds": args.interval_seconds,
            "chronological_holdout_start": args.holdout_start,
            "outcome_definition": "at horizon close: signed move > threshold=CONTINUATION; < -threshold=REVERSAL; otherwise SIDEWAYS",
            "note": "Empirical frequencies split chronologically by event date; holdout is descriptive only, not calibrated probabilities or a profitability claim; no costs/slippage or confidence intervals.",
        },
        "eligible_impulse_events": eligible,
        "groups": report,
        "chronological_splits": split_report,
        "unresolved_tail_events_excluded": len(pending),
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": output["status"],
                "rows_read": total_rows,
                "eligible_impulse_events": eligible,
                "group_count": len(report),
                "train_events": sum(
                    sum(group.values()) for group in split_counts["TRAIN"].values()
                ),
                "holdout_events": sum(
                    sum(group.values()) for group in split_counts["HOLDOUT"].values()
                ),
                "unresolved_tail_events_excluded": len(pending),
                "output": str(destination),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
