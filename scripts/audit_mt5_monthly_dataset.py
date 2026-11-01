from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

EXPECTED_COLUMNS = [
    "time", "open", "high", "low", "close",
    "tick_volume", "spread", "real_volume",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_dataset(root: Path) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    context_path = root / "source_context.json"
    if not manifest_path.is_file() or not context_path.is_file():
        raise FileNotFoundError("manifest.json and source_context.json are required")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    context = json.loads(context_path.read_text(encoding="utf-8"))
    if (manifest.get("symbol"), manifest.get("timeframe")) != ("XAUUSD", "M1"):
        raise ValueError("Source manifest is not XAUUSD M1")
    if context.get("account_server") != "FTMO-Demo":
        raise ValueError("Source context does not identify FTMO-Demo")

    chunks = manifest.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("Manifest chunks are missing")

    errors: list[str] = []
    chunk_names = [Path(str(item.get("file", ""))).name for item in chunks]
    expected_names = set(chunk_names)
    if chunk_names != sorted(chunk_names):
        errors.append("CHUNKS_NOT_IN_CHRONOLOGICAL_ORDER")
    actual_names = {item.name for item in root.glob("XAUUSD_M1_*.csv")}
    for extra_name in sorted(actual_names - expected_names):
        errors.append(f"UNMANIFESTED_FILE:{extra_name}")
    inventory: list[dict[str, Any]] = []
    year_hashes: dict[str, Any] = {}
    year_rows: dict[str, int] = {}
    year_first: dict[str, int] = {}
    year_last: dict[str, int] = {}
    stream_hash = hashlib.sha256()
    total_rows = 0
    duplicate_timestamps = 0
    non_increasing_intervals = 0
    invalid_ohlc_rows = 0
    negative_tick_volume_rows = 0
    negative_real_volume_rows = 0
    negative_spread_rows = 0
    timestamp_parse_failures = 0
    out_of_range_rows = 0
    requested_start_epoch = int(pd.Timestamp(manifest["requested_start"]).timestamp())
    requested_end_epoch = int(pd.Timestamp(manifest["requested_end"]).timestamp())
    gaps_gt_60s = 0
    gaps_60_300s = 0
    gaps_300_900s = 0
    gaps_900_21600s = 0
    gaps_over_21600s = 0
    max_gap_seconds = 0
    previous_last_epoch: int | None = None
    spread_parts: list[np.ndarray] = []
    zero_spread_rows = 0
    spread_over_100_points_rows = 0
    spread_over_500_points_rows = 0
    seen_names: set[str] = set()

    for chunk in chunks:
        name = Path(str(chunk.get("file", ""))).name
        if not name or name in seen_names:
            errors.append(f"INVALID_OR_DUPLICATE_CHUNK_NAME:{name}")
            continue
        seen_names.add(name)
        path = root / name
        if not path.is_file():
            errors.append(f"MISSING_FILE:{name}")
            continue

        raw_hash = sha256_file(path)
        if raw_hash != chunk.get("sha256"):
            errors.append(f"SHA256_MISMATCH:{name}")
        raw_bytes = path.read_bytes()
        stream_hash.update(raw_bytes)
        year = name.split("_")[2]
        year_hashes.setdefault(year, hashlib.sha256()).update(raw_bytes)

        frame = pd.read_csv(path)
        if frame.empty:
            errors.append(f"EMPTY_CHUNK:{name}")
            continue
        if list(frame.columns) != EXPECTED_COLUMNS:
            errors.append(f"SCHEMA_MISMATCH:{name}")
            continue
        if len(frame) != int(chunk.get("rows", -1)):
            errors.append(f"ROW_COUNT_MISMATCH:{name}")

        epoch = pd.to_numeric(frame["time"], errors="coerce")
        timestamp_parse_failures += int(epoch.isna().sum())
        valid_epoch = epoch.dropna().astype("int64")
        out_of_range_rows += int(((valid_epoch < requested_start_epoch) | (valid_epoch > requested_end_epoch)).sum())
        if len(valid_epoch):
            first_epoch = int(valid_epoch.iloc[0])
            last_epoch = int(valid_epoch.iloc[-1])
            if first_epoch != int(chunk.get("first_epoch", first_epoch)):
                errors.append(f"FIRST_EPOCH_MISMATCH:{name}")
            if last_epoch != int(chunk.get("last_epoch", last_epoch)):
                errors.append(f"LAST_EPOCH_MISMATCH:{name}")
            if not valid_epoch.is_monotonic_increasing:
                errors.append(f"NON_MONOTONIC_CHUNK:{name}")
            duplicate_timestamps += int(valid_epoch.duplicated().sum())
            if previous_last_epoch is not None:
                delta = first_epoch - previous_last_epoch
                if delta <= 0:
                    non_increasing_intervals += 1
                elif delta > 60:
                    gaps_gt_60s += 1
                    if delta <= 300:
                        gaps_60_300s += 1
                    elif delta <= 900:
                        gaps_300_900s += 1
                    elif delta <= 21600:
                        gaps_900_21600s += 1
                    else:
                        gaps_over_21600s += 1
                    max_gap_seconds = max(max_gap_seconds, delta)
            previous_last_epoch = last_epoch
            year_first[year] = min(year_first.get(year, first_epoch), first_epoch)
            year_last[year] = max(year_last.get(year, last_epoch), last_epoch)
        year_rows[year] = year_rows.get(year, 0) + len(frame)

        diffs = valid_epoch.diff().dropna()
        non_increasing_intervals += int((diffs <= 0).sum())
        gap_values = diffs[diffs > 60]
        gaps_gt_60s += len(gap_values)
        if len(gap_values):
            max_gap_seconds = max(max_gap_seconds, int(gap_values.max()))
            gaps_60_300s += int(((gap_values > 60) & (gap_values <= 300)).sum())
            gaps_300_900s += int(((gap_values > 300) & (gap_values <= 900)).sum())
            gaps_900_21600s += int(((gap_values > 900) & (gap_values <= 21600)).sum())
            gaps_over_21600s += int((gap_values > 21600).sum())

        prices = frame[["open", "high", "low", "close"]].to_numpy(dtype=float)
        finite_prices = np.isfinite(prices).all(axis=1)
        invalid = (~finite_prices) | (prices[:, 0] <= 0) | (prices[:, 1] <= 0) | (prices[:, 2] <= 0) | (prices[:, 3] <= 0)
        invalid |= prices[:, 1] < np.maximum(prices[:, 0], prices[:, 3])
        invalid |= prices[:, 2] > np.minimum(prices[:, 0], prices[:, 3])
        invalid |= prices[:, 1] < prices[:, 2]
        invalid_ohlc_rows += int(invalid.sum())

        for col, counter in (("tick_volume", "tick"), ("real_volume", "real"), ("spread", "spread")):
            values = pd.to_numeric(frame[col], errors="coerce").to_numpy(dtype=float)
            bad = (~np.isfinite(values)) | (values < 0)
            if counter == "tick":
                negative_tick_volume_rows += int(bad.sum())
            elif counter == "real":
                negative_real_volume_rows += int(bad.sum())
            else:
                negative_spread_rows += int(bad.sum())
                clean = values[~bad]
                spread_parts.append(clean)
                zero_spread_rows += int((clean == 0).sum())
                spread_over_100_points_rows += int((clean > 100).sum())
                spread_over_500_points_rows += int((clean > 500).sum())

        total_rows += len(frame)
        timestamps = pd.to_datetime(valid_epoch, unit="s", utc=True)
        inventory.append({
            "file": name,
            "sha256": raw_hash,
            "rows": len(frame),
            "first_utc": timestamps.min().isoformat() if len(timestamps) else None,
            "last_utc": timestamps.max().isoformat() if len(timestamps) else None,
        })

    spread = np.concatenate(spread_parts) if spread_parts else np.array([], dtype=float)
    quantiles = {
        str(q): float(np.quantile(spread, q))
        for q in (0, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1)
    } if len(spread) else {}
    inventory_bytes = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
    yearly_slices = {
        year: {
            "rows": year_rows[year],
            "first_utc": pd.Timestamp(year_first[year], unit="s", tz="UTC").isoformat(),
            "last_utc": pd.Timestamp(year_last[year], unit="s", tz="UTC").isoformat(),
            "concatenated_csv_bytes_sha256": year_hashes[year].hexdigest(),
        }
        for year in sorted(year_hashes)
    }
    report: dict[str, Any] = {
        "schema_version": 1,
        "source": manifest.get("source"),
        "account_server": context.get("account_server"),
        "symbol": manifest.get("symbol"),
        "timeframe": manifest.get("timeframe"),
        "requested_start": manifest.get("requested_start"),
        "requested_end": manifest.get("requested_end"),
        "actual_first_utc": inventory[0]["first_utc"] if inventory else None,
        "actual_last_utc": inventory[-1]["last_utc"] if inventory else None,
        "terminal": manifest.get("terminal"),
        "symbol_metadata": manifest.get("symbol_metadata"),
        "monthly_files": len(inventory),
        "manifest_chunks": len(chunks),
        "row_count": total_rows,
        "timestamp_parse_failures": timestamp_parse_failures,
        "out_of_range_rows": out_of_range_rows,
        "duplicate_timestamps": duplicate_timestamps,
        "non_increasing_intervals": non_increasing_intervals,
        "gaps_gt_60s": gaps_gt_60s,
        "gaps_60_to_300_seconds": gaps_60_300s,
        "gaps_301_to_900_seconds": gaps_300_900s,
        "gaps_901_to_21600_seconds": gaps_900_21600s,
        "gaps_over_21600_seconds": gaps_over_21600s,
        "max_gap_seconds": max_gap_seconds,
        "invalid_ohlc_rows": invalid_ohlc_rows,
        "negative_tick_volume_rows": negative_tick_volume_rows,
        "negative_real_volume_rows": negative_real_volume_rows,
        "negative_spread_rows": negative_spread_rows,
        "spread_points_quantiles": quantiles,
        "spread_zero_rows": zero_spread_rows,
        "spread_over_100_points_rows": spread_over_100_points_rows,
        "spread_over_500_points_rows": spread_over_500_points_rows,
        "manifest_sha256": sha256_file(manifest_path),
        "source_context_sha256": sha256_file(context_path),
        "concatenated_csv_bytes_sha256": stream_hash.hexdigest(),
        "inventory_sha256": hashlib.sha256(inventory_bytes).hexdigest(),
        "yearly_slices": yearly_slices,
        "chunks": inventory,
        "errors": errors,
    }
    report["integrity_pass"] = not errors and all(report[key] == 0 for key in (
        "timestamp_parse_failures", "out_of_range_rows", "duplicate_timestamps", "non_increasing_intervals",
        "invalid_ohlc_rows", "negative_tick_volume_rows", "negative_real_volume_rows",
        "negative_spread_rows",
    )) and len(inventory) == len(chunks)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Independent audit of monthly MT5 OHLC datasets")
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = audit_dataset(args.input_dir)
    output = args.output or (args.input_dir / "independent_audit.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "chunks"}, indent=2))
    print(f"AUDIT_REPORT={output}")
    print(f"INTEGRITY_PASS={report['integrity_pass']}")
    return 0 if report["integrity_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
