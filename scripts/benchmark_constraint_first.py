"""Benchmark the native constraint-first kernel on a real CSV close column.

Example:
  python scripts/benchmark_constraint_first.py path/to/xauusd_m1.csv --candles 1000000 --candidates 100000
The input file must contain a chronological 'close' column. No synthetic market
data is generated and the script does not download data or submit orders.
"""

from __future__ import annotations

import argparse
import csv
import platform
import sys
import time
from pathlib import Path

import numpy as np

from researchos.engines.quant.python.cpp_quant_engine.constraint_first import evaluate_candidates


def read_closes(path: Path, limit: int | None) -> np.ndarray:
    values: list[float] = []
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "close" not in reader.fieldnames:
            raise ValueError("CSV must contain a 'close' column")
        for row in reader:
            values.append(float(row["close"]))
            if limit is not None and len(values) >= limit:
                break
    return np.ascontiguousarray(values, dtype=np.float64)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--candles", type=int, default=1_000_000)
    parser.add_argument("--candidates", type=int, default=100_000)
    parser.add_argument("--max-unique-horizons", type=int, default=64)
    parser.add_argument("--minimum-probability", type=float, default=0.0)
    parser.add_argument("--minimum-samples", type=int, default=1)
    args = parser.parse_args()

    if args.candles < 3 or args.candidates < 1 or args.max_unique_horizons < 1:
        parser.error("--candles must be >= 3, --candidates >= 1, and --max-unique-horizons >= 1")

    closes = read_closes(args.csv_path, args.candles)
    if len(closes) < 3:
        parser.error("CSV contains fewer than 3 close prices")

    candidate_ids = np.arange(args.candidates, dtype=np.int64)
    horizons = (candidate_ids % args.max_unique_horizons + 1).astype(np.int32)
    targets = (5.0 + (candidate_ids % 100) * 5.0).astype(np.float64)
    directions = np.where(candidate_ids % 2 == 0, 1, -1).astype(np.int32)

    started = time.perf_counter()
    result = evaluate_candidates(
        closes,
        targets,
        horizons,
        directions,
        max_unique_horizons=args.max_unique_horizons,
        minimum_probability=args.minimum_probability,
        minimum_samples=args.minimum_samples,
    )
    elapsed = time.perf_counter() - started

    print(f"commit: {__import__('os').environ.get('GITHUB_SHA', 'set GITHUB_SHA for exact revision')}")
    print(f"input: {args.csv_path.resolve()}")
    print(f"python: {sys.version.split()[0]} ({platform.platform()})")
    print(f"candles: {result['candle_count']}")
    print(f"candidates: {args.candidates}")
    print(f"unique_horizons: {result['unique_horizons']}")
    print(f"elapsed_seconds: {elapsed:.6f}")
    print(f"candles_per_second: {result['candle_count'] / elapsed:.2f}")
    print(f"candidates_per_second: {args.candidates / elapsed:.2f}")
    print(f"survivors: {len(result['survivor_indices'])}")
    print(f"rejected: {len(result['rejected_indices'])}")
    print(f"filter: probability >= {args.minimum_probability}, sample_size >= {args.minimum_samples}")
    print(f"warning: {result['warning']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
