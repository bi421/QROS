"""Run an auditable, leakage-safe XAUUSD M1 walk-forward probability study.

The output is an evidence-bearing research artifact: every OOS prediction is
traceable to its event id, validation fold, training membership, source-artifact
SHA-256, and explicit temporal embargo rule.

This stage estimates a raw empirical probability only. It makes no claim of
predictive edge, profitability, calibration, or trading validity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must be timezone-aware: {value}")
    return parsed.astimezone(timezone.utc)


def _complete_rows(report: dict) -> list[dict]:
    rows = []
    seen_ids: set[str] = set()
    for event in report.get("events_data", []):
        event_id = event.get("event_id")
        outcome = event.get("outcome") or {}
        endpoint = (outcome.get("data_availability") or {}).get("realized_end_1d")
        label = outcome.get("hit_threshold_1d")
        if endpoint is None or label is None:
            continue
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("Every complete event must have a non-empty event_id")
        if event_id in seen_ids:
            raise ValueError(f"Duplicate event_id: {event_id}")
        if not isinstance(label, bool):
            raise ValueError(f"Outcome label must be boolean: {event_id}")
        timestamp = _parse_time(event["timestamp"])
        realized_end = _parse_time(endpoint)
        if realized_end <= timestamp:
            raise ValueError(f"Outcome endpoint is not forward-only: {event_id}")
        direction = event.get("direction")
        if direction not in {"bullish", "bearish"}:
            raise ValueError(f"Invalid event direction: {event_id}")
        seen_ids.add(event_id)
        rows.append(
            {
                "event_id": event_id,
                "timestamp": timestamp,
                "realized_end": realized_end,
                "direction": direction,
                "label": int(label),
            }
        )
    return sorted(rows, key=lambda row: (row["timestamp"], row["event_id"]))


def _estimate(train: list[dict], row: dict) -> tuple[float, str]:
    """Estimate conditional hit probability from prior training outcomes only."""
    if not train:
        raise ValueError("Cannot estimate probability without training observations")
    same_direction = [item for item in train if item["direction"] == row["direction"]]
    if not same_direction:
        raise ValueError(
            f"No prior observations for validation direction {row['direction']}; refusing fallback"
        )
    return sum(item["label"] for item in same_direction) / len(same_direction), "direction_conditional"


def _score(predictions: list[float], labels: list[int]) -> dict[str, float | int]:
    if not labels or len(predictions) != len(labels):
        raise ValueError("Predictions and labels must be non-empty and aligned")
    if any(not 0.0 <= p <= 1.0 for p in predictions):
        raise ValueError("Predictions must lie in [0, 1]")
    brier = sum((p - y) ** 2 for p, y in zip(predictions, labels)) / len(labels)
    log_loss = 0.0
    for p, y in zip(predictions, labels):
        p = min(max(p, 1e-15), 1.0 - 1e-15)
        log_loss += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return {
        "sample_count": len(labels),
        "brier_score": round(brier, 10),
        "log_loss": round(log_loss / len(labels), 10),
        "observed_rate": round(sum(labels) / len(labels), 10),
    }


def run(
    input_path: Path,
    output_path: Path,
    train_size: int,
    validation_size: int,
    step_size: int,
    holdout_size: int = 500,
) -> dict:
    if train_size <= 0 or validation_size <= 0 or step_size <= 0:
        raise ValueError("train_size, validation_size and step_size must be positive")
    if holdout_size <= 0:
        raise ValueError("holdout_size must be positive")
    if step_size < validation_size:
        raise ValueError("step_size must be >= validation_size so OOS validation windows do not overlap")
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    raw = input_path.read_bytes()
    source_sha256 = hashlib.sha256(raw).hexdigest()
    report = json.loads(raw.decode("utf-8"))
    contract = report.get("contract", {})
    dataset = report.get("dataset", {})
    if contract.get("asset") != "XAUUSD" or contract.get("timeframe") != "M1":
        raise ValueError("Input artifact is not the XAUUSD M1 contract")
    if contract.get("label") != "hit_threshold_1d":
        raise ValueError("Input artifact does not use the required 1-day label")
    if dataset.get("sha256") in (None, ""):
        raise ValueError("Input artifact is missing dataset SHA-256 identity")

    rows = _complete_rows(report)
    minimum_events = train_size + validation_size + holdout_size
    if len(rows) < minimum_events:
        raise ValueError(
            "Insufficient complete events for requested walk-forward plus holdout configuration"
        )

    pre_holdout_rows = rows[:-holdout_size]
    holdout_rows = rows[-holdout_size:]
    holdout_start = holdout_rows[0]["timestamp"]
    holdout_end = holdout_rows[-1]["timestamp"]

    folds = []
    all_predictions: list[float] = []
    all_baseline: list[float] = []
    all_labels: list[int] = []
    all_validation_ids: set[str] = set()
    start = 0
    while start + train_size + validation_size <= len(pre_holdout_rows):
        val_start_idx = start + train_size
        val_end_idx = val_start_idx + validation_size
        validation = rows[val_start_idx:val_end_idx]
        validation_start = validation[0]["timestamp"]
        train_pool = pre_holdout_rows[:val_start_idx]
        train = [item for item in train_pool if item["realized_end"] < validation_start]
        if not train:
            raise RuntimeError(f"No leakage-safe training observations for fold starting {validation_start.isoformat()}")
        train_ids = {item["event_id"] for item in train}
        validation_ids = {item["event_id"] for item in validation}
        if train_ids & validation_ids:
            raise RuntimeError("Training and validation event sets overlap")
        if all_validation_ids & validation_ids:
            raise RuntimeError("Validation event appears in more than one OOS fold")

        train_rate = sum(item["label"] for item in train) / len(train)
        fold_predictions: list[float] = []
        fold_labels: list[int] = []
        prediction_records = []
        methods: dict[str, int] = {}
        for row in validation:
            probability, method = _estimate(train, row)
            if not 0.0 <= probability <= 1.0:
                raise RuntimeError("Probability outside [0, 1]")
            fold_predictions.append(probability)
            fold_labels.append(row["label"])
            methods[method] = methods.get(method, 0) + 1
            prediction_records.append(
                {
                    "event_id": row["event_id"],
                    "timestamp": row["timestamp"].isoformat(),
                    "direction": row["direction"],
                    "probability": round(probability, 12),
                    "label": row["label"],
                }
            )

        fold_score = _score(fold_predictions, fold_labels)
        baseline_score = _score([train_rate] * len(fold_labels), fold_labels)
        folds.append(
            {
                "fold": len(folds) + 1,
                "train_start": train[0]["timestamp"].isoformat(),
                "train_end": train[-1]["timestamp"].isoformat(),
                "validation_start": validation[0]["timestamp"].isoformat(),
                "validation_end": validation[-1]["timestamp"].isoformat(),
                "train_events": len(train),
                "validation_events": len(validation),
                "embargoed_events": len(train_pool) - len(train),
                "training_event_ids": [item["event_id"] for item in train],
                "training_outcome_rate": round(train_rate, 12),
                "prediction_methods": methods,
                "predictions": prediction_records,
                "model": fold_score,
                "baseline": baseline_score,
            }
        )
        all_predictions.extend(fold_predictions)
        all_baseline.extend([train_rate] * len(fold_labels))
        all_labels.extend(fold_labels)
        all_validation_ids.update(validation_ids)
        start += step_size

    if not folds:
        raise RuntimeError("No walk-forward folds were produced before the final holdout")

    holdout_train = [item for item in pre_holdout_rows if item["realized_end"] < holdout_start]
    if not holdout_train:
        raise RuntimeError(
            f"No leakage-safe training observations for final holdout starting {holdout_start.isoformat()}"
        )
    holdout_train_rate = sum(item["label"] for item in holdout_train) / len(holdout_train)
    holdout_predictions: list[float] = []
    holdout_labels: list[int] = []
    holdout_prediction_records = []
    holdout_methods: dict[str, int] = {}
    for row in holdout_rows:
        probability, method = _estimate(holdout_train, row)
        if not 0.0 <= probability <= 1.0:
            raise RuntimeError("Holdout probability outside [0, 1]")
        holdout_predictions.append(probability)
        holdout_labels.append(row["label"])
        holdout_methods[method] = holdout_methods.get(method, 0) + 1
        holdout_prediction_records.append(
            {
                "event_id": row["event_id"],
                "timestamp": row["timestamp"].isoformat(),
                "direction": row["direction"],
                "probability": round(probability, 12),
                "label": row["label"],
            }
        )

    holdout_model_score = _score(holdout_predictions, holdout_labels)
    holdout_baseline_score = _score([holdout_train_rate] * len(holdout_labels), holdout_labels)
    model_score = _score(all_predictions, all_labels)
    baseline_score = _score(all_baseline, all_labels)
    report_out = {
        "stage": "M1_WALK_FORWARD_RAW_PROBABILITY",
        "scientific_status": "OOS_RAW_PROBABILITY_ONLY_NO_EDGE_CLAIM",
        "source_artifact": {"path": str(input_path), "sha256": source_sha256},
        "dataset": dataset,
        "contract": contract,
        "split": {
            "train_size": train_size,
            "validation_size": validation_size,
            "step_size": step_size,
            "holdout_size": holdout_size,
            "embargo_rule": "training realized_end < validation_start",
            "holdout_rule": "holdout training realized_end < holdout_start",
            "fit_uses_validation_labels": False,
            "fit_uses_holdout_labels": False,
            "validation_windows_overlap": False,
            "holdout_is_disjoint": True,
        },
        "methodology": {
            "forecast_horizon": "1d",
            "feature_availability_timestamp": "event timestamp",
            "selection_policy": "single fixed direction_conditional estimator; no parameter selection",
            "multiple_testing_policy": "not_applicable_single_fixed_estimator",
            "stopping_rule": "none; evaluate the full pre-registered chronological range",
            "replication_rule": "final independent temporal holdout",
            "cost_assumptions": {
                "spread": "not applicable to this probability-only stage",
                "slippage": "not applicable to this probability-only stage",
                "commission": "not applicable to this probability-only stage",
            },
        },
        "folds": folds,
        "aggregate": {
            "scope": "walk_forward_validation_only_excludes_final_holdout",
            "model": model_score,
            "baseline": baseline_score,
        },
        "holdout": {
            "start": holdout_rows[0]["timestamp"].isoformat(),
            "end": holdout_rows[-1]["timestamp"].isoformat(),
            "holdout_events": len(holdout_rows),
            "pre_holdout_events": len(pre_holdout_rows),
            "training_events": len(holdout_train),
            "embargoed_training_events": len(pre_holdout_rows) - len(holdout_train),
            "training_start": holdout_train[0]["timestamp"].isoformat(),
            "training_end": holdout_train[-1]["timestamp"].isoformat(),
            "training_max_realized_end": max(item["realized_end"] for item in holdout_train).isoformat(),
            "training_outcome_rate": round(holdout_train_rate, 12),
            "prediction_methods": holdout_methods,
            "predictions": holdout_prediction_records,
            "model": holdout_model_score,
            "baseline": holdout_baseline_score,
        },
        "audit": {
            "complete_events": len(rows),
            "pre_holdout_events": len(pre_holdout_rows),
            "oos_unique_validation_events": len(all_validation_ids),
            "holdout_events": len(holdout_rows),
            "holdout_is_disjoint_from_validation": True,
            "probabilities_in_unit_interval": True,
            "training_validation_overlap": False,
            "validation_event_reuse": False,
            "all_training_labels_realized_before_validation": True,
            "all_holdout_training_labels_realized_before_holdout": True,
            "source_sha256_verified_from_bytes": True,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report_out, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/xauusd_m1_walkforward.json"))
    parser.add_argument("--train-size", type=int, default=2000)
    parser.add_argument("--validation-size", type=int, default=500)
    parser.add_argument("--step-size", type=int, default=500)
    parser.add_argument("--holdout-size", type=int, default=500)
    args = parser.parse_args()
    result = run(
        args.input,
        args.output,
        args.train_size,
        args.validation_size,
        args.step_size,
        args.holdout_size,
    )
    print(f"Folds: {len(result['folds'])}")
    print(f"OOS validation samples: {result['aggregate']['model']['sample_count']}")
    print(f"Final holdout samples: {result['holdout']['model']['sample_count']}")
    print(f"Model Brier: {result['aggregate']['model']['brier_score']}")
    print(f"Baseline Brier: {result['aggregate']['baseline']['brier_score']}")
    print(f"Model LogLoss: {result['aggregate']['model']['log_loss']}")
    print(f"Baseline LogLoss: {result['aggregate']['baseline']['log_loss']}")
    print(f"Audit: {result['audit']}")
    print(f"Artifact: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
