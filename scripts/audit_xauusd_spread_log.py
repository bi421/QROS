"""Audit the retained MT5 XAUUSD spread field without assuming broker point conversion.

The source CSV remains the spread log; this writes a compact provenance/statistics report.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "mt5" / "xauusd" / "XAUUSD_M1_2021_2025_MT5.csv"
OUTPUT = ROOT / "artifacts" / "xauusd_spread_log_audit_20261017.json"


def run() -> dict[str, Any]:
    raw = SOURCE.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    frame = pl.read_csv(SOURCE, try_parse_dates=False, columns=["time", "spread"])
    spread = frame["spread"].cast(pl.Float64)
    if spread.null_count() or not spread.is_finite().all() or (spread < 0).any():
        raise ValueError("Spread log contains null, non-finite, or negative observations")
    report = {
        "schema_version": "xauusd-spread-log-audit.v1",
        "source_path": str(SOURCE.relative_to(ROOT)),
        "source_sha256": digest,
        "source_rows": frame.height,
        "time_start": frame["time"][0],
        "time_end": frame["time"][-1],
        "field": "spread",
        "raw_unit": "MT5 native spread points; conversion to XAUUSD price units not independently established",
        "observation_count": spread.len(),
        "zero_spread_count": int((spread == 0).sum()),
        "positive_spread_count": int((spread > 0).sum()),
        "minimum": float(spread.min()),
        "median": float(spread.quantile(0.50)),
        "p90": float(spread.quantile(0.90)),
        "p95": float(spread.quantile(0.95)),
        "p99": float(spread.quantile(0.99)),
        "maximum": float(spread.max()),
        "commission_model": "NOT_FOUND_IN_SOURCE_DATA",
        "slippage_model": "NOT_FOUND_IN_SOURCE_DATA",
        "spread_price_conversion": "NOT_VERIFIED",
        "all_in_costs_verified": False,
        "gate_eligible": False,
        "limitations": [
            "Per-bar MT5 spread field is not proof of executable entry/exit spread at each trade timestamp.",
            "Point/tick size and broker contract specification are not declared in this artifact.",
            "Commission and slippage evidence are missing; do not mark costs verified.",
        ],
    }
    OUTPUT.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
