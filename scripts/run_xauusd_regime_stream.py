"""Process large XAUUSD OHLC CSV files in bounded-memory streaming mode."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import pandas as pd

from researchos.orchestration.incremental_regime import IncrementalRegimeEngine


def _sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def process_csv(
    path: Path,
    *,
    chunksize: int = 100_000,
    lookback: int = 100,
    adx_period: int = 14,
    hurst_refresh_every: int = 10,
) -> dict[str, object]:
    if chunksize < 1:
        raise ValueError("chunksize must be positive")
    engine = IncrementalRegimeEngine(
        lookback=lookback,
        adx_period=adx_period,
        hurst_refresh_every=hurst_refresh_every,
    )
    rows = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    last_timestamp_value = None
    result: dict[str, object] | None = None
    started = time.perf_counter()
    column_map: dict[str, str] | None = None

    for chunk in pd.read_csv(path, chunksize=chunksize, memory_map=True):
        if column_map is None:
            column_map = {str(c).strip().lower().strip("<>"): str(c) for c in chunk.columns}
            if not all(name in column_map for name in ("high", "low", "close")):
                raise ValueError("CSV requires high, low, close columns")
            if "timestamp" in column_map:
                time_columns = [column_map["timestamp"]]
            elif "datetime" in column_map:
                time_columns = [column_map["datetime"]]
            elif "date" in column_map and "time" in column_map:
                time_columns = [column_map["date"], column_map["time"]]
            elif "date" in column_map:
                time_columns = [column_map["date"]]
            elif "time" in column_map:
                time_columns = [column_map["time"]]
            else:
                raise ValueError("CSV requires timestamp, datetime, date/time, date, or time")

        if len(time_columns) == 2:
            time_values = (
                chunk[time_columns[0]].astype(str) + " " + chunk[time_columns[1]].astype(str)
            )
            time_label = "date+time"
        else:
            time_values = chunk[time_columns[0]]
            time_label = time_columns[0]
        parsed = pd.to_datetime(time_values, errors="coerce", utc=True)
        if parsed.isna().any():
            raise ValueError("CSV contains invalid timestamps")
        if not parsed.is_monotonic_increasing:
            raise ValueError("CSV timestamps are duplicate or not chronological")
        if last_timestamp_value is not None and parsed.iloc[0] <= last_timestamp_value:
            raise ValueError("CSV timestamps are duplicate or not chronological across chunks")
        if first_timestamp is None:
            first_timestamp = parsed.iloc[0].isoformat()
        last_timestamp = parsed.iloc[-1].isoformat()
        last_timestamp_value = parsed.iloc[-1]

        high = chunk[column_map["high"]].to_numpy(dtype=float, copy=False)
        low = chunk[column_map["low"]].to_numpy(dtype=float, copy=False)
        close = chunk[column_map["close"]].to_numpy(dtype=float, copy=False)
        for h, lo, c in zip(high, low, close, strict=True):
            updated = engine.update(h, lo, c)
            if updated is not None:
                result = updated
        rows += len(chunk)

    stream_elapsed = time.perf_counter() - started
    if rows == 0:
        raise ValueError("CSV has no candle rows")
    hash_started = time.perf_counter()
    input_sha256 = _sha256_file(path)
    hash_elapsed = time.perf_counter() - hash_started
    total_elapsed = time.perf_counter() - started
    return {
        "schema_version": "1.0",
        "report_type": "xauusd_incremental_regime_stream",
        "input": {
            "file_name": path.name,
            "sha256": input_sha256,
            "row_count": rows,
            "timestamp_column": time_label,
            "first_timestamp_utc": first_timestamp,
            "last_timestamp_utc": last_timestamp,
            "chunksize": chunksize,
            "memory_map_enabled": True,
        },
        "performance": {
            "stream_elapsed_seconds": stream_elapsed,
            "sha256_elapsed_seconds": hash_elapsed,
            "total_elapsed_seconds_including_sha256": total_elapsed,
            "rows_per_second_excluding_sha256": rows / stream_elapsed if stream_elapsed else None,
            "mean_microseconds_per_candle_excluding_sha256": stream_elapsed * 1_000_000 / rows,
            "benchmark_note": "Observed local runtime; excludes the separate full-file SHA-256 pass from per-candle throughput.",
        },
        "result": result
        or {
            "status": "INSUFFICIENT_EVIDENCE",
            "reason": "not enough candles to complete indicator warm-up",
            "execution_enabled": False,
        },
        "claims": {
            "historical_scan_milliseconds_for_one_billion_rows": False,
            "new_candle_incremental_update_target": "sub-millisecond, hardware and workload dependent",
            "probabilities_calibrated": False,
            "trading_edge_proven": False,
            "order_execution_enabled": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--chunksize", type=int, default=100_000)
    parser.add_argument("--lookback", type=int, default=100)
    parser.add_argument("--adx-period", type=int, default=14)
    parser.add_argument("--hurst-refresh-every", type=int, default=10)
    args = parser.parse_args()
    report = process_csv(
        args.csv_path,
        chunksize=args.chunksize,
        lookback=args.lookback,
        adx_period=args.adx_period,
        hurst_refresh_every=args.hurst_refresh_every,
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
