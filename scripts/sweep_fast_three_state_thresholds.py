"""Training-only parameter sensitivity; holdout data is never used for selection."""

from __future__ import annotations

import csv
import itertools
import json
from pathlib import Path

from researchos.orchestration.fast_three_state import FastThreeState


def main() -> None:
    path = Path("data/phase52/xauusd.csv")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    close_key = next(key for key in rows[0] if key.strip().lower() == "close")
    date_key = next(
        (key for key in rows[0] if key.strip().lower() in {"date", "timestamp", "datetime"}), None
    )
    closes = [float(row[close_key]) for row in rows]
    split = int(len(closes) * 0.7)
    train_closes = closes[:split]
    records = []

    for lookback, efficiency in itertools.product((16, 24, 32, 48), (0.20, 0.30, 0.35, 0.40)):
        engine = FastThreeState(
            lookback=lookback,
            efficiency_threshold=efficiency,
            min_move_bps=5.0,
        )
        labels = [engine.update(close) for close in train_closes]
        counts = {state: labels.count(state) for state in (-1, 0, 1)}
        horizon_metrics = {}
        for horizon in (5, 10, 20):
            per_state = {}
            for state in (-1, 1):
                hits = total = 0
                for index in range(lookback - 1, split - horizon):
                    if labels[index] != state:
                        continue
                    move = closes[index + horizon] / closes[index] - 1.0
                    hits += int(move < 0 if state == -1 else move > 0)
                    total += 1
                per_state[str(state)] = {
                    "n": total,
                    "hit_rate": round(hits / total, 4) if total else None,
                }
            horizon_metrics[str(horizon)] = per_state
        records.append(
            {
                "lookback": lookback,
                "efficiency_threshold": efficiency,
                "train_state_counts": {str(state): counts[state] for state in (-1, 0, 1)},
                "train_state_share": {
                    str(state): round(counts[state] / split, 3) for state in (-1, 0, 1)
                },
                "directional_hit_rates": horizon_metrics,
            }
        )

    print(
        json.dumps(
            {
                "input": str(path),
                "rows": len(closes),
                "train_rows": split,
                "train_end_date": rows[split - 1][date_key] if date_key else None,
                "holdout_excluded_from_parameter_sweep": True,
                "candidate_count": len(records),
                "warning": "Sensitivity only. Labels are overlapping regime windows; hit rates are descriptive, not proof of edge. Parameters should not be selected from one metric.",
                "candidates": records,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
