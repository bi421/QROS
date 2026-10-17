"""Create a one-shot, immutable forward-test preregistration from current historical artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from researchos.orchestration.vectorized_backtest import load_ohlcv_csv

ROOT = Path(__file__).resolve().parents[1]
M15_SOURCE = Path(r"C:\Users\User\Documents\XAUUSDM15.csv")
ENGINE_REPORT = ROOT / "artifacts/qros_follow_original_engine_rerun_20261017.json"
COST_REPORT = ROOT / "artifacts/qros_follow_19_cost_reassessment_20261017.json"
COST_CONFIG = ROOT / "config/costs.yaml"
ENGINE_CODE = ROOT / "researchos/orchestration/vectorized_backtest.py"
COST_CODE = ROOT / "researchos/orchestration/xauusd_cost_model.py"
OUTPUT = ROOT / "config/forward_validation_preregistration_20261017.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(force: bool = False) -> dict:
    if OUTPUT.exists() and not force:
        raise FileExistsError(f"Forward preregistration already exists; refusing to rewrite: {OUTPUT}")
    required = (M15_SOURCE, ENGINE_REPORT, COST_REPORT, COST_CONFIG, ENGINE_CODE, COST_CODE)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"PREREGISTRATION_INPUTS_MISSING:{missing}")
    cost_report = json.loads(COST_REPORT.read_text(encoding="utf-8-sig"))
    pairs = [item["params"] for item in cost_report["historical_19"]]
    if len(pairs) != 19:
        raise ValueError(f"EXPECTED_19_FROZEN_PAIRS_GOT_{len(pairs)}")
    m15 = load_ohlcv_csv(M15_SOURCE)
    latest = max(m15["timestamp"])
    latest_text = str(latest)
    latest_date = datetime.fromisoformat(latest_text.replace("Z", "+00:00")).replace(tzinfo=None)
    start = (latest_date.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
    end = start + timedelta(days=92)
    payload = {
        "schema_version": "qros-forward-preregistration.v1",
        "created_date": "2026-10-17",
        "status": "PREREGISTERED_WAITING_FOR_FORWARD_DATA",
        "instrument": "XAUUSD",
        "timeframe": "M15",
        "source_timestamp_timezone": "naive timestamps as supplied by original broker export; do not reinterpret as UTC",
        "historical_source_latest_timestamp": latest_text,
        "forward_start_in_source_time": start.isoformat(sep=" "),
        "single_fixed_evaluation_cutoff_in_source_time": end.isoformat(sep=" "),
        "rules_mutable": False,
        "strategy_or_parameter_changes_allowed": False,
        "interim_performance_lookups_allowed": False,
        "number_of_evaluations": 1,
        "minimum_exact_spread_trades_per_direction_per_pair": 100,
        "minimum_calendar_days": 92,
        "if_sample_minimum_not_met": "INCONCLUSIVE; do not extend cutoff or alter rules in this preregistration",
        "frozen_pairs": pairs,
        "frozen_pair_count": len(pairs),
        "entry_rule": "Signal confirmed at M15 close; enter at next M15 bar open; order type market_entry.",
        "exit_rule": "Keep original M15 TP/SL barrier prices, stop-first tie policy, and horizon unchanged; classify TP as tp_limit, SL as sl_stop, timeout as market_exit.",
        "spread_rule": "Use same bar-level spread and executable side accounting; reject trades with incomplete exit-minute spread instead of proxy filling.",
        "cost_model": {
            "commission_source": "frozen config/costs.yaml; still assumed, not broker verified",
            "slippage_source": "frozen per-order-type assumptions in config/costs.yaml; not observed fills",
            "cost_config_sha256": sha256(COST_CONFIG),
            "cost_model_code_sha256": sha256(COST_CODE),
        },
        "statistics": {
            "primary_endpoint": "mean net return per trade after spread, commission, and order-type slippage",
            "paired_endpoint": "FOLLOW minus REVERSE net expectancy",
            "fdr_method": "Benjamini-Hochberg",
            "paired_family_size": 19,
            "directional_absolute_edge_family_size": 38,
            "alpha": 0.05,
            "block_bootstrap_replicates": 1000,
            "block_length": "per-pair ceiling of larger median FOLLOW/REVERSE holding period, computed by frozen code",
            "no_reoptimization": True,
        },
        "source_hashes": {
            str(M15_SOURCE): sha256(M15_SOURCE),
            str(ENGINE_REPORT.relative_to(ROOT)): sha256(ENGINE_REPORT),
            str(COST_REPORT.relative_to(ROOT)): sha256(COST_REPORT),
            str(ENGINE_CODE.relative_to(ROOT)): sha256(ENGINE_CODE),
            str(COST_CODE.relative_to(ROOT)): sha256(COST_CODE),
        },
        "historical_selection_overlaps_prior_data": True,
        "interpretation_limit": "Forward results apply only to this frozen family and cost assumptions; a failed/insufficient test is not proof that all XAUUSD strategies lack edge.",
        "execution_authorized": False,
    }
    OUTPUT.write_text(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    payload["preregistration_sha256"] = sha256(OUTPUT)
    print(json.dumps({
        "output": str(OUTPUT.relative_to(ROOT)),
        "preregistration_sha256": payload["preregistration_sha256"],
        "latest_historical_timestamp": latest_text,
        "forward_start": payload["forward_start_in_source_time"],
        "fixed_cutoff": payload["single_fixed_evaluation_cutoff_in_source_time"],
        "frozen_pairs": len(pairs),
        "status": payload["status"],
    }, indent=2))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Only for an explicitly authorized new preregistration version.")
    args = parser.parse_args()
    run(force=args.force)
