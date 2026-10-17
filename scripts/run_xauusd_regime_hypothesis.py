"""Run an opt-in, low-memory holdout hypothesis test on XAUUSD CSV candles."""

from __future__ import annotations

import argparse
import json
import os
from collections import deque
from pathlib import Path

import pandas as pd

from researchos.orchestration.incremental_regime import IncrementalRegimeEngine
from researchos.orchestration.regime_hypothesis import evaluate_regime_directional_value


def run_test(
    csv_path: Path,
    *,
    chunksize: int = 10_000,
    horizon: int = 5,
    max_observations: int = 20_000,
    bootstrap_replicates: int = 999,
    lookback: int = 100,
    adx_period: int = 14,
    seed: int = 20261016,
) -> dict[str, object]:
    if chunksize < 1:
        raise ValueError("chunksize must be positive")
    if max_observations < 100:
        raise ValueError("max_observations must be >= 100")
    engine = IncrementalRegimeEngine(lookback=lookback, adx_period=adx_period)
    capacity = 2 * max_observations + horizon + 1
    tail_closes: deque[float] = deque(maxlen=capacity)
    tail_states: deque[str | None] = deque(maxlen=capacity)
    rows = 0
    columns: dict[str, str] | None = None
    previous_timestamp = None
    first_timestamp = None
    last_timestamp = None

    for chunk in pd.read_csv(csv_path, chunksize=chunksize, memory_map=True):
        if columns is None:
            columns = {str(c).strip().lower().strip("<>"): str(c) for c in chunk.columns}
            if not all(key in columns for key in ("high", "low", "close")):
                raise ValueError("CSV requires high, low, close columns")
            if "timestamp" in columns:
                time_cols = [columns["timestamp"]]
            elif "datetime" in columns:
                time_cols = [columns["datetime"]]
            elif "date" in columns and "time" in columns:
                time_cols = [columns["date"], columns["time"]]
            elif "date" in columns:
                time_cols = [columns["date"]]
            elif "time" in columns:
                time_cols = [columns["time"]]
            else:
                raise ValueError("CSV requires a timestamp or date/time column")

        raw_times = (
            chunk[time_cols[0]].astype(str) + " " + chunk[time_cols[1]].astype(str)
            if len(time_cols) == 2
            else chunk[time_cols[0]]
        )
        timestamps = pd.to_datetime(raw_times, errors="coerce", utc=True)
        if timestamps.isna().any() or not timestamps.is_monotonic_increasing:
            raise ValueError("CSV timestamps are invalid, duplicate, or not chronological")
        if previous_timestamp is not None and timestamps.iloc[0] <= previous_timestamp:
            raise ValueError("CSV timestamps are duplicate or not chronological across chunks")
        if first_timestamp is None:
            first_timestamp = timestamps.iloc[0].isoformat()
        last_timestamp = timestamps.iloc[-1].isoformat()
        previous_timestamp = timestamps.iloc[-1]

        highs = chunk[columns["high"]].to_numpy(dtype=float, copy=False)
        lows = chunk[columns["low"]].to_numpy(dtype=float, copy=False)
        closes = chunk[columns["close"]].to_numpy(dtype=float, copy=False)
        for high, low, close in zip(highs, lows, closes, strict=True):
            result = engine.update(high, low, close)
            tail_closes.append(float(close))
            tail_states.append(result["current_state"] if result is not None else None)
            rows += 1

    if rows == 0:
        raise ValueError("CSV has no candle rows")
    tail_start_row_index = rows - len(tail_closes)
    report = evaluate_regime_directional_value(
        list(tail_states),
        list(tail_closes),
        horizon=horizon,
        holdout_fraction=0.5,
        bootstrap_replicates=bootstrap_replicates,
        seed=seed,
        max_observations=max_observations,
    )
    if report.get("status") == "COMPLETED":
        report["holdout_start_index"] = int(report["holdout_start_index"]) + tail_start_row_index
        report["holdout_end_index_exclusive"] = (
            int(report["holdout_end_index_exclusive"]) + tail_start_row_index
        )
    return {
        "schema_version": "1.0",
        "report_type": "xauusd_regime_hypothesis_test",
        "input": {
            "file_name": csv_path.name,
            "row_count_processed": rows,
            "first_timestamp_utc": first_timestamp,
            "last_timestamp_utc": last_timestamp,
            "chunksize": chunksize,
            "tail_buffer_capacity": capacity,
            "tail_buffer_rows_retained": len(tail_closes),
        },
        "hypothesis_test": report,
        "resource_policy": {
            "network_access": False,
            "database_access": False,
            "order_execution": False,
            "runs_only_when_cli_is_invoked": True,
            "windows_priority": "BELOW_NORMAL_BEST_EFFORT",
            "maximum_holdout_observations": max_observations,
            "note": "Offline opt-in CPU work; best-effort below-normal Windows priority; not called by live/incremental update path.",
        },
    }


def _set_best_effort_low_priority() -> bool:
    """Ask Windows to schedule this optional offline job below normal priority."""
    if os.name != "nt":
        return False
    try:
        import ctypes

        below_normal_priority_class = 0x00004000
        kernel32 = ctypes.windll.kernel32
        return bool(
            kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), below_normal_priority_class)
        )
    except (AttributeError, OSError):
        return False


def main() -> int:
    _set_best_effort_low_priority()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--chunksize", type=int, default=10_000)
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--max-observations", type=int, default=20_000)
    parser.add_argument("--bootstrap-replicates", type=int, default=999)
    parser.add_argument("--lookback", type=int, default=100)
    parser.add_argument("--adx-period", type=int, default=14)
    parser.add_argument("--seed", type=int, default=20261016)
    args = parser.parse_args()
    report = run_test(
        args.csv_path,
        chunksize=args.chunksize,
        horizon=args.horizon,
        max_observations=args.max_observations,
        bootstrap_replicates=args.bootstrap_replicates,
        lookback=args.lookback,
        adx_period=args.adx_period,
        seed=args.seed,
    )
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
        print("REPORT_WRITTEN=" + str(args.output))
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
