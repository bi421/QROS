"""Create a fail-closed reproducibility envelope for the real XAUUSD M1 chain.

The envelope binds raw dataset bytes, source event/outcome artifact bytes,
walk-forward result bytes, research contract, split parameters, code commit,
and an independently supplied audit result. It proves lineage and
reproducibility metadata only; it does not prove predictive edge.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

SCIENTIFIC_STATUS = "REPRODUCIBILITY_LINEAGE_ONLY_NO_EDGE_CLAIM"
REQUIRED_CONTRACT = ("XAUUSD", "M1", "hit_threshold_1d")


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash_object(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON artifact: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"artifact root must be an object: {path}")
    return value


def build_envelope(
    raw_csv: Path,
    source_artifact: Path,
    result_artifact: Path,
    audit_artifact: Path,
    code_commit: str,
) -> dict:
    raw_sha = _sha256(raw_csv)
    source_sha = _sha256(source_artifact)
    result_sha = _sha256(result_artifact)
    audit_sha = _sha256(audit_artifact)
    source = _load(source_artifact)
    result = _load(result_artifact)
    audit = _load(audit_artifact)

    contract = source.get("contract")
    result_contract = result.get("contract")
    if not isinstance(contract, dict) or not isinstance(result_contract, dict):
        raise ValueError("source/result contract is missing")
    if (contract.get("asset"), contract.get("timeframe"), contract.get("label")) != REQUIRED_CONTRACT:
        raise ValueError("source contract is not the frozen XAUUSD M1 contract")
    if result_contract != contract:
        raise ValueError("result contract differs from source contract")

    source_dataset = source.get("dataset") or {}
    result_dataset = result.get("dataset") or {}
    declared_dataset_sha = source_dataset.get("sha256")
    if declared_dataset_sha != raw_sha:
        raise ValueError("source dataset SHA-256 does not match supplied raw CSV bytes")
    if result_dataset.get("sha256") != raw_sha:
        raise ValueError("result dataset SHA-256 does not match supplied raw CSV bytes")

    declared_source_sha = (result.get("source_artifact") or {}).get("sha256")
    if declared_source_sha != source_sha:
        raise ValueError("result source_artifact SHA-256 does not match supplied source artifact")

    if result.get("stage") != "M1_WALK_FORWARD_RAW_PROBABILITY":
        raise ValueError("unexpected walk-forward result stage")
    if result.get("scientific_status") != "OOS_RAW_PROBABILITY_ONLY_NO_EDGE_CLAIM":
        raise ValueError("walk-forward scientific boundary is missing or changed")
    if audit.get("status") != "PASS":
        raise ValueError("independent source-to-result audit is not PASS")
    if audit.get("source_sha256") != source_sha:
        raise ValueError("audit source SHA-256 does not match supplied source artifact")
    if audit.get("result_artifact_sha256") != result_sha:
        raise ValueError("audit result SHA-256 does not match supplied result artifact")

    if not isinstance(code_commit, str) or len(code_commit) != 40 or any(c not in "0123456789abcdef" for c in code_commit):
        raise ValueError("code_commit must be the exact 40-character Git commit SHA")

    split = result.get("split")
    if not isinstance(split, dict):
        raise ValueError("walk-forward split configuration is missing")
    split_fields = (
        "train_size",
        "validation_size",
        "step_size",
        "holdout_size",
        "embargo_rule",
        "holdout_rule",
        "fit_uses_validation_labels",
        "fit_uses_holdout_labels",
        "validation_windows_overlap",
        "holdout_is_disjoint",
    )
    split_snapshot = {key: split.get(key) for key in split_fields}
    if any(split_snapshot[key] is None for key in split_fields):
        raise ValueError("walk-forward split configuration is incomplete")
    if split_snapshot["fit_uses_validation_labels"] is not False:
        raise ValueError("validation labels must not be used for fitting")
    if split_snapshot["validation_windows_overlap"] is not False:
        raise ValueError("validation windows must not overlap")
    if split_snapshot["fit_uses_holdout_labels"] is not False:
        raise ValueError("holdout labels must not be used for fitting")
    if split_snapshot["holdout_is_disjoint"] is not True:
        raise ValueError("final holdout must be disjoint from walk-forward validation")

    methodology = result.get("methodology")
    if not isinstance(methodology, dict):
        raise ValueError("methodology contract is missing")
    methodology_fields = (
        "forecast_horizon",
        "feature_availability_timestamp",
        "selection_policy",
        "multiple_testing_policy",
        "stopping_rule",
        "replication_rule",
        "cost_assumptions",
    )
    if any(methodology.get(key) is None for key in methodology_fields):
        raise ValueError("methodology contract is incomplete")

    holdout = result.get("holdout")
    if not isinstance(holdout, dict):
        raise ValueError("final holdout artifact is missing")
    holdout_fields = (
        "start",
        "end",
        "holdout_events",
        "training_events",
        "training_end",
        "training_max_realized_end",
        "training_outcome_rate",
        "predictions",
        "model",
        "baseline",
    )
    if any(holdout.get(key) is None for key in holdout_fields):
        raise ValueError("final holdout artifact is incomplete")
    if holdout.get("holdout_events") != split_snapshot["holdout_size"]:
        raise ValueError("holdout event count does not match holdout_size")
    if len(holdout.get("predictions", [])) != split_snapshot["holdout_size"]:
        raise ValueError("holdout prediction count does not match holdout_size")

    contract_snapshot = {
        "asset": contract["asset"],
        "timeframe": contract["timeframe"],
        "event": contract.get("event"),
        "label": contract["label"],
        "horizon_days": contract.get("horizon_days"),
        "threshold_return": contract.get("threshold_return"),
        "price_field": contract.get("price_field"),
        "direction_aware": contract.get("direction_aware"),
    }
    parameter_snapshot = {
        "split": split_snapshot,
        "methodology": methodology,
        "holdout": {
            "start": holdout["start"],
            "end": holdout["end"],
            "holdout_events": holdout["holdout_events"],
            "pre_holdout_events": holdout.get("pre_holdout_events"),
            "training_events": holdout["training_events"],
            "embargoed_training_events": holdout.get("embargoed_training_events"),
            "training_start": holdout.get("training_start"),
            "training_end": holdout["training_end"],
            "training_max_realized_end": holdout["training_max_realized_end"],
        },
        "contract": contract_snapshot,
    }
    envelope_core = {
        "schema_version": 1,
        "stage": "XAUUSD_M1_EVIDENCE_ENVELOPE",
        "scientific_status": SCIENTIFIC_STATUS,
        "lineage": {
            "raw_dataset": {"path": str(raw_csv), "sha256": raw_sha},
            "source_artifact": {"path": str(source_artifact), "sha256": source_sha},
            "result_artifact": {"path": str(result_artifact), "sha256": result_sha},
            "independent_audit": {"path": str(audit_artifact), "sha256": audit_sha, "status": "PASS"},
        },
        "identity": {
            "dataset_sha256": raw_sha,
            "contract_hash": _hash_object(contract_snapshot),
            "parameter_hash": _hash_object(parameter_snapshot),
            "code_commit": code_commit,
        },
        "contract": contract_snapshot,
        "parameters": parameter_snapshot,
        "runtime": {
            "python_version": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
    }
    envelope_hash = _hash_object(envelope_core)
    return {**envelope_core, "envelope_sha256": envelope_hash}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-csv", type=Path, required=True)
    parser.add_argument("--source-artifact", type=Path, required=True)
    parser.add_argument("--result-artifact", type=Path, required=True)
    parser.add_argument("--audit-artifact", type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    envelope = build_envelope(args.raw_csv, args.source_artifact, args.result_artifact, args.audit_artifact, args.code_commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(envelope, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
