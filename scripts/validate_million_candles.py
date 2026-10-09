"""Validate exactly N real CSV rows through QROS native C++ quant and Turing filters.

Required columns: timestamp_ns, close, bid, ask, bid_volume, ask_volume, trade_volume.
No market microstructure fields are synthesized. Input must be chronological.
Example:
  python scripts/validate_million_candles.py xauusd.csv --candles 1000000
This is an execution/data-integrity validation, not proof of a profitable trading edge.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np

from researchos.engines.quant.python.cpp_quant_engine.constraint_first import evaluate_candidates


REQUIRED_COLUMNS = (
    "timestamp_ns",
    "close",
    "bid",
    "ask",
    "bid_volume",
    "ask_volume",
    "trade_volume",
)


def load_market_rows(path: Path, count: int) -> dict[str, np.ndarray]:
    arrays: dict[str, np.ndarray] = {
        "timestamp_ns": np.empty(count, dtype=np.int64),
        "close": np.empty(count, dtype=np.float64),
        "bid": np.empty(count, dtype=np.float64),
        "ask": np.empty(count, dtype=np.float64),
        "bid_volume": np.empty(count, dtype=np.float64),
        "ask_volume": np.empty(count, dtype=np.float64),
        "trade_volume": np.empty(count, dtype=np.float64),
    }
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError("CSV header is missing")
        missing = sorted(set(REQUIRED_COLUMNS) - set(reader.fieldnames))
        if missing:
            raise ValueError(f"CSV missing required columns: {', '.join(missing)}")

        previous_timestamp: int | None = None
        loaded = 0
        for row in reader:
            if loaded == count:
                break
            timestamp = int(row["timestamp_ns"])
            if previous_timestamp is not None and timestamp <= previous_timestamp:
                raise ValueError(
                    f"timestamps must be strictly increasing; violation at row {loaded + 2}"
                )
            previous_timestamp = timestamp
            arrays["timestamp_ns"][loaded] = timestamp
            for key in REQUIRED_COLUMNS[1:]:
                arrays[key][loaded] = float(row[key])
            loaded += 1

    if loaded != count:
        raise ValueError(f"required {count:,} candles, CSV contains only {loaded:,}")
    for key, values in arrays.items():
        if key != "timestamp_ns" and not np.isfinite(values).all():
            raise ValueError(f"column {key!r} contains non-finite values")
    if (arrays["close"] <= 0).any() or (arrays["bid"] <= 0).any() or (arrays["ask"] <= 0).any():
        raise ValueError("close, bid and ask prices must be positive")
    if (arrays["ask"] < arrays["bid"]).any():
        raise ValueError("ask must be >= bid")
    if (arrays["bid_volume"] < 0).any() or (arrays["ask_volume"] < 0).any() or (arrays["trade_volume"] < 0).any():
        raise ValueError("volume columns must be non-negative")
    return arrays


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--candles", type=int, default=1_000_000)
    parser.add_argument("--candidates", type=int, default=1_000)
    parser.add_argument("--max-unique-horizons", type=int, default=16)
    parser.add_argument("--target-bps", type=float, default=25.0)
    parser.add_argument("--minimum-probability", type=float, default=0.0)
    parser.add_argument("--minimum-samples", type=int, default=1)
    parser.add_argument("--max-spread", type=float, default=1.0)
    parser.add_argument("--min-total-depth", type=float, default=0.0)
    parser.add_argument("--min-trade-volume", type=float, default=0.0)
    parser.add_argument("--min-abs-imbalance", type=float, default=0.05)
    parser.add_argument("--min-persistence", type=int, default=2)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--beta", type=float, default=0.10)
    args = parser.parse_args()

    if args.candles < 3 or args.candidates < 1 or args.max_unique_horizons < 1:
        parser.error("--candles must be >= 3; candidates and unique horizons must be positive")
    if args.max_unique_horizons > args.candles - 2:
        parser.error("--max-unique-horizons cannot exceed candles - 2")
    if args.target_bps <= 0 or args.min_persistence < 1:
        parser.error("target-bps and min-persistence must be positive")

    source = args.csv_path.resolve(strict=True)
    data = load_market_rows(source, args.candles)
    source_digest = sha256_file(source)

    candidate_ids = np.arange(args.candidates, dtype=np.int64)
    targets = np.full(args.candidates, args.target_bps, dtype=np.float64)
    horizons = (candidate_ids % args.max_unique_horizons + 1).astype(np.int32)
    directions = np.where(candidate_ids % 2 == 0, 1, -1).astype(np.int32)

    started = time.perf_counter()
    quant_result = evaluate_candidates(
        data["close"], targets, horizons, directions,
        max_unique_horizons=args.max_unique_horizons,
        minimum_probability=args.minimum_probability,
        minimum_samples=args.minimum_samples,
    )
    quant_elapsed = time.perf_counter() - started
    if quant_result["candle_count"] != args.candles:
        raise RuntimeError("native quant engine did not report the requested candle count")
    if len(quant_result["probability"]) != args.candidates:
        raise RuntimeError("native quant engine returned an unexpected candidate count")

    from cpp_quant_engine import cpp_quant_backend

    config = cpp_quant_backend.TuringFilterConfig()
    config.max_spread = args.max_spread
    config.min_total_depth = args.min_total_depth
    config.min_trade_volume = args.min_trade_volume
    config.min_abs_imbalance = args.min_abs_imbalance
    config.min_persistence = args.min_persistence
    config.max_samples = 64
    config.event_probability_h = 0.80
    config.event_probability_not_h = 0.20
    config.contradiction_probability_h = 0.20
    config.contradiction_probability_not_h = 0.80
    thresholds = cpp_quant_backend.TuringFilterEngine.thresholds_from_error_rates(
        args.alpha, args.beta
    )
    config.lower_deciban = thresholds.lower_deciban
    config.upper_deciban = thresholds.upper_deciban

    decisions = np.empty(args.candles, dtype=np.uint8)
    started = time.perf_counter()
    cpp_quant_backend.turing_filter_batch(
        np.ascontiguousarray(data["timestamp_ns"]),
        np.ascontiguousarray(data["bid"]),
        np.ascontiguousarray(data["ask"]),
        np.ascontiguousarray(data["bid_volume"]),
        np.ascontiguousarray(data["ask_volume"]),
        np.ascontiguousarray(data["trade_volume"]),
        config,
        True,
        decisions,
    )
    turing_elapsed = time.perf_counter() - started
    if len(decisions) != args.candles:
        raise RuntimeError("native Turing filter did not return one decision per candle")

    print("validation: PASS")
    print(f"revision: {os.environ.get('GITHUB_SHA', 'local/unpinned')}")
    print(f"input: {source}")
    print(f"input_sha256: {source_digest}")
    print(f"python: {sys.version.split()[0]}")
    print(f"platform: {platform.platform()}")
    print(f"candles_loaded_and_validated: {args.candles}")
    print(f"timestamp_range_ns: {int(data['timestamp_ns'][0])}..{int(data['timestamp_ns'][-1])}")
    print(f"native_quant_candidates: {args.candidates}")
    print(f"native_quant_unique_horizons: {quant_result['unique_horizons']}")
    print(f"native_quant_seconds: {quant_elapsed:.6f}")
    print(f"native_quant_candles_per_second: {args.candles / quant_elapsed:.2f}")
    print(f"native_quant_survivors: {len(quant_result['survivor_indices'])}")
    print(f"native_quant_rejected: {len(quant_result['rejected_indices'])}")
    print(f"turing_filter_seconds: {turing_elapsed:.6f}")
    print(f"turing_candles_per_second: {args.candles / turing_elapsed:.2f}")
    print(f"turing_decision_counts: drop={int(np.count_nonzero(decisions == 0))}, "
          f"continue={int(np.count_nonzero(decisions == 1))}, "
          f"accept={int(np.count_nonzero(decisions == 2))}, "
          f"reject={int(np.count_nonzero(decisions == 3))}")
    print(f"turing_evidence_deciban_per_confirming_event: "
          f"{cpp_quant_backend.TuringFilterEngine.evidence_deciban(0.80, 0.20):.12f}")
    print(f"turing_sprt_bounds_deciban: lower={config.lower_deciban:.12f}, "
          f"upper={config.upper_deciban:.12f}")
    print("scope: execution/data-integrity validation only; not a profitable-edge claim")
    print("quant_warning: " + quant_result["warning"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
