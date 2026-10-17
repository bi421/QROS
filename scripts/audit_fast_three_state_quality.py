"""Descriptive, chronological holdout check for FastThreeState labels."""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

from researchos.orchestration.fast_three_state import FastThreeState


def main() -> None:
    path = Path("data/phase52/xauusd.csv")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    close_key = next((key for key in rows[0] if key.strip().lower() == "close"), None)
    date_key = next(
        (key for key in rows[0] if key.strip().lower() in {"date", "timestamp", "datetime"}), None
    )
    if close_key is None:
        raise ValueError("CSV requires Close column")
    closes = [float(row[close_key]) for row in rows]
    dates = [row[date_key] for row in rows] if date_key else []
    engine = FastThreeState()
    labels = [engine.update(close) for close in closes]
    split = int(len(closes) * 0.7)
    horizons = (1, 5, 10)
    result = {
        "input": str(path),
        "rows": len(closes),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "holdout_start_index": split,
        "holdout_start_date": dates[split] if dates else None,
        "holdout_fraction": 0.3,
        "thresholds": {
            "lookback_bars": engine.lookback,
            "efficiency_threshold": engine.efficiency_threshold,
            "minimum_net_move_bps": engine.min_move_bps,
        },
        "interpretation": "Descriptive close-to-close returns only. No costs, confidence intervals, parameter tuning, or proof of trading edge.",
        "horizons": {},
    }
    for horizon in horizons:
        grouped = {state: [] for state in (-1, 0, 1)}
        all_returns = []
        for index in range(split, len(closes) - horizon):
            state = labels[index]
            if index < 31:
                continue
            forward_bps = (closes[index + horizon] / closes[index] - 1.0) * 10_000.0
            grouped[state].append(forward_bps)
            all_returns.append(forward_bps)
        metrics = {}
        for state, values in grouped.items():
            if not values:
                metrics[str(state)] = {"count": 0}
                continue
            metrics[str(state)] = {
                "count": len(values),
                "mean_forward_return_bps": round(statistics.mean(values), 4),
                "median_forward_return_bps": round(statistics.median(values), 4),
                "positive_return_rate": round(sum(value > 0 for value in values) / len(values), 4),
                "directional_hit_rate": (
                    round(sum(value > 0 for value in values) / len(values), 4)
                    if state == 1
                    else round(sum(value < 0 for value in values) / len(values), 4)
                    if state == -1
                    else None
                ),
                "mean_absolute_return_bps": round(
                    statistics.mean(abs(value) for value in values), 4
                ),
            }
        result["horizons"][str(horizon)] = {
            "sample_count": len(all_returns),
            "overall_mean_forward_return_bps": round(statistics.mean(all_returns), 4)
            if all_returns
            else None,
            "by_state": metrics,
        }
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
