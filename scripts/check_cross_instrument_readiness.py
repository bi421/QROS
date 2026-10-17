"""Fail-closed readiness check for running the frozen cost pipeline on XAGUSD/EURUSD."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/qros_cross_instrument_readiness_20261017.json"
INSTRUMENTS = {
    "XAGUSD": {
        "csv": ROOT / "data/mt5/xagusd/XAGUSD_M1_2021_2025_MT5.csv",
        "manifest": ROOT / "data/mt5/xagusd/XAGUSD_M1_2021_2025_MT5.manifest.json",
        "cost_config": ROOT / "config/costs_xagusd.yaml",
    },
    "EURUSD": {
        "csv": ROOT / "data/mt5/eurusd/EURUSD_M1_2021_2025_MT5.csv",
        "manifest": ROOT / "data/mt5/eurusd/EURUSD_M1_2021_2025_MT5.manifest.json",
        "cost_config": ROOT / "config/costs_eurusd.yaml",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(name: str, paths: dict) -> dict:
    missing = [key for key, path in paths.items() if not path.is_file()]
    result = {
        "instrument": name,
        "status": "BLOCKED_MISSING_DATA_OR_METADATA" if missing else "INPUTS_PRESENT_REQUIRES_SCHEMA_VALIDATION",
        "missing_inputs": missing,
        "inputs": {key: str(path.relative_to(ROOT)) for key, path in paths.items()},
        "execution_authorized": False,
    }
    if not missing:
        result["sha256"] = {key: sha256(path) for key, path in paths.items()}
    return result


def run() -> dict:
    report = {
        "schema_version": "qros-cross-instrument-readiness.v1",
        "status": "BLOCKED",
        "strategy_changed": False,
        "results": {name: inspect(name, paths) for name, paths in INSTRUMENTS.items()},
        "blocker": "No local XAGUSD/EURUSD spread-bearing M1 CSV, symbol manifest, or symbol-specific cost config was found. XAUUSD metadata must not be reused for other symbols.",
        "required_before_comparison": [
            "MT5 M1 OHLC plus per-bar spread for each instrument, with source timestamp/timezone and SHA-256",
            "Symbol point, digits, contract size, tick size/value and quote-side semantics from the exact broker symbol specification",
            "Commission schedule by side/lot and account currency",
            "Order-type slippage observations or clearly labelled assumptions",
            "Same frozen 19 parameter pairs and identical evaluation windows; no instrument-specific retuning",
            "Report data coverage, missingness, spread distribution, sample size, net expectancy and cost multipliers",
        ],
        "execution_authorized": False,
    }
    OUTPUT.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
