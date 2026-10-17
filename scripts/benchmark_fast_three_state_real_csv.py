"""Benchmark the minimal hot path against a local historical XAUUSD CSV."""

from __future__ import annotations

import csv
import hashlib
import math
import statistics
import time
from pathlib import Path

from researchos.orchestration.fast_three_state import FastThreeState


def load_close_csv(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV has no header")
        names = {name.strip().lower(): name for name in reader.fieldnames}
        close_name = names.get("close")
        date_name = names.get("date") or names.get("timestamp") or names.get("datetime")
        if close_name is None:
            raise ValueError("CSV requires a Close column")
        closes = []
        first_date = last_date = None
        for row in reader:
            value = float(row[close_name])
            if not math.isfinite(value) or value <= 0:
                raise ValueError("CSV has invalid close value")
            closes.append(value)
            if first_date is None and date_name:
                first_date = row[date_name]
            if date_name:
                last_date = row[date_name]
    return closes, first_date, last_date, digest.hexdigest()


def main():
    path = Path("data/phase52/xauusd.csv")
    closes, first_date, last_date, digest = load_close_csv(path)
    if len(closes) < 32:
        raise ValueError("need at least 32 rows")
    repeats = 50
    elapsed_per_bar = []
    final_states = []
    for _ in range(repeats):
        engine = FastThreeState()
        start = time.perf_counter_ns()
        output = [engine.update(value) for value in closes]
        elapsed_per_bar.append((time.perf_counter_ns() - start) / len(closes))
        final_states.append(output[-1])
    ordered = sorted(elapsed_per_bar)

    engine = FastThreeState()
    for value in closes[-100:]:
        engine.update(value)
    individual = []
    for index in range(10_000):
        start = time.perf_counter_ns()
        engine.update(closes[index % len(closes)])
        individual.append(time.perf_counter_ns() - start)
    individual.sort()

    counts = {state: 0 for state in (-1, 0, 1)}
    engine = FastThreeState()
    for value in closes:
        counts[engine.update(value)] += 1

    print(
        {
            "input_file": str(path),
            "sha256": digest,
            "rows": len(closes),
            "first_date": first_date,
            "last_date": last_date,
            "repeats": repeats,
            "batch_median_ns_per_candle": round(statistics.median(elapsed_per_bar), 1),
            "batch_p95_ns_per_candle_across_repeats": round(
                ordered[math.ceil(0.95 * repeats) - 1], 1
            ),
            "median_rows_per_second": round(1e9 / statistics.median(elapsed_per_bar), 1),
            "individual_call_latency_ns_including_timer_overhead": {
                "p50": individual[int(0.50 * (len(individual) - 1))],
                "p95": individual[int(0.95 * (len(individual) - 1))],
                "p99": individual[int(0.99 * (len(individual) - 1))],
                "samples": len(individual),
            },
            "state_counts": counts,
            "final_state": final_states[-1],
            "limitations": "Close-only D1 CSV, not M1 live feed or end-to-end latency; thresholds are unvalidated.",
        }
    )


if __name__ == "__main__":
    main()
