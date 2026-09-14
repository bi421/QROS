"""Independent source-to-result audit for the XAUUSD M1 walk-forward artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path


def _time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"naive timestamp: {value}")
    return dt.astimezone(timezone.utc)


def _rows(report: dict) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for event in report.get("events_data", []):
        outcome = event.get("outcome") or {}
        availability = outcome.get("data_availability") or {}
        endpoint = availability.get("realized_end_1d")
        label = outcome.get("hit_threshold_1d")
        if endpoint is None or label is None:
            continue
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("complete event has invalid event_id")
        if event_id in seen:
            raise ValueError(f"duplicate event_id: {event_id}")
        if not isinstance(label, bool):
            raise ValueError(f"label is not boolean: {event_id}")
        direction = event.get("direction")
        if direction not in {"bullish", "bearish"}:
            raise ValueError(f"invalid direction: {event_id}")
        timestamp = _time(event["timestamp"])
        realized_end = _time(endpoint)
        if realized_end <= timestamp:
            raise ValueError(f"realized endpoint is not forward-only: {event_id}")
        seen.add(event_id)
        rows.append(
            {
                "event_id": event_id,
                "timestamp": timestamp,
                "realized_end": realized_end,
                "direction": direction,
                "label": int(label),
            }
        )
    return sorted(rows, key=lambda r: (r["timestamp"], r["event_id"]))


def _score(predictions: list[float], labels: list[int]) -> dict[str, float | int]:
    if not labels or len(predictions) != len(labels):
        raise ValueError("score inputs are empty or misaligned")
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in predictions):
        raise ValueError("invalid probability in score inputs")
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


def audit(source_path: Path, result_path: Path) -> dict:
    source_raw = source_path.read_bytes()
    result_raw = result_path.read_bytes()
    source = json.loads(source_raw.decode("utf-8"))
    result = json.loads(result_raw.decode("utf-8"))
    failures: list[str] = []

    expected_source_hash = hashlib.sha256(source_raw).hexdigest()
    declared_source_hash = (result.get("source_artifact") or {}).get("sha256")
    if declared_source_hash != expected_source_hash:
        failures.append("source artifact SHA-256 does not match supplied source")

    if result.get("stage") != "M1_WALK_FORWARD_RAW_PROBABILITY":
        failures.append("wrong result stage")
    if result.get("scientific_status") != "OOS_RAW_PROBABILITY_ONLY_NO_EDGE_CLAIM":
        failures.append("scientific boundary changed or missing")

    contract = source.get("contract", {})
    required_contract = ("XAUUSD", "M1", "hit_threshold_1d")
    if (
        contract.get("asset"),
        contract.get("timeframe"),
        contract.get("label"),
    ) != required_contract:
        failures.append("source research contract mismatch")
    result_contract = result.get("contract") or {}
    if (
        result_contract.get("asset"),
        result_contract.get("timeframe"),
        result_contract.get("label"),
    ) != required_contract:
        failures.append("result research contract mismatch")
    if result_contract != contract:
        failures.append("result contract differs from source contract")

    source_dataset = source.get("dataset") or {}
    result_dataset = result.get("dataset") or {}
    source_dataset_sha = source_dataset.get("sha256")
    if not isinstance(source_dataset_sha, str) or len(source_dataset_sha) != 64:
        failures.append("source dataset SHA-256 is missing or malformed")
    if result_dataset.get("sha256") != source_dataset_sha:
        failures.append("result dataset SHA-256 differs from source dataset identity")

    try:
        rows = _rows(source)
    except (KeyError, TypeError, ValueError) as exc:
        return {"status": "FAIL", "failures": [f"source reconstruction failed: {exc}"]}

    split = result.get("split") or {}
    try:
        train_size = int(split["train_size"])
        validation_size = int(split["validation_size"])
        step_size = int(split["step_size"])
    except (KeyError, TypeError, ValueError) as exc:
        return {"status": "FAIL", "failures": [f"invalid split configuration: {exc}"]}
    if min(train_size, validation_size, step_size) <= 0:
        failures.append("split sizes must be positive")
    if step_size < validation_size:
        failures.append("validation windows overlap by configuration")

    expected_folds: list[dict] = []
    start = 0
    while start + train_size + validation_size <= len(rows) and train_size > 0:
        val_start_idx = start + train_size
        val_end_idx = val_start_idx + validation_size
        validation = rows[val_start_idx:val_end_idx]
        validation_start = validation[0]["timestamp"]
        train_pool = rows[:val_start_idx]
        train = [r for r in train_pool if r["realized_end"] < validation_start]
        if not train:
            failures.append(
                f"expected fold {len(expected_folds)+1} has no leakage-safe training rows"
            )
            break
        expected_folds.append(
            {"train": train, "validation": validation, "embargoed": len(train_pool) - len(train)}
        )
        start += step_size

    actual_folds = result.get("folds") or []
    if len(actual_folds) != len(expected_folds):
        failures.append(
            f"fold count mismatch: expected {len(expected_folds)}, got {len(actual_folds)}"
        )

    actual_predictions: list[tuple[float, int]] = []
    seen_prediction_ids: set[str] = set()
    for index, expected in enumerate(expected_folds):
        if index >= len(actual_folds):
            break
        actual = actual_folds[index]
        expected_train_ids = [r["event_id"] for r in expected["train"]]
        actual_train_ids = actual.get("training_event_ids")
        if set(actual_train_ids or []) != set(expected_train_ids):
            failures.append(
                f"fold {index+1}: training membership differs from source reconstruction"
            )
        if actual.get("train_events") != len(expected["train"]):
            failures.append(f"fold {index+1}: train_events mismatch")
        if actual.get("validation_events") != len(expected["validation"]):
            failures.append(f"fold {index+1}: validation_events mismatch")
        if actual.get("embargoed_events") != expected["embargoed"]:
            failures.append(f"fold {index+1}: embargo count mismatch")
        if actual.get("train_start") != expected["train"][0]["timestamp"].isoformat():
            failures.append(f"fold {index+1}: train_start mismatch")
        if actual.get("train_end") != expected["train"][-1]["timestamp"].isoformat():
            failures.append(f"fold {index+1}: train_end mismatch")
        if actual.get("validation_start") != expected["validation"][0]["timestamp"].isoformat():
            failures.append(f"fold {index+1}: validation_start mismatch")
        if actual.get("validation_end") != expected["validation"][-1]["timestamp"].isoformat():
            failures.append(f"fold {index+1}: validation_end mismatch")

        train = expected["train"]
        rate = sum(r["label"] for r in train) / len(train)
        if actual.get("training_outcome_rate") != round(rate, 12):
            failures.append(f"fold {index+1}: training outcome rate mismatch")

        source_by_id = {r["event_id"]: r for r in expected["validation"]}
        predictions = actual.get("predictions") or []
        if len(predictions) != len(expected["validation"]):
            failures.append(f"fold {index+1}: prediction row count mismatch")

        fold_predictions: list[float] = []
        fold_labels: list[int] = []
        fold_baseline: list[float] = []
        for prediction in predictions:
            event_id = prediction.get("event_id")
            source_row = source_by_id.get(event_id)
            if source_row is None:
                failures.append(
                    f"fold {index+1}: prediction event not in expected validation set: {event_id}"
                )
                continue
            if event_id in seen_prediction_ids:
                failures.append(f"fold {index+1}: validation event reused: {event_id}")
            seen_prediction_ids.add(event_id)
            if prediction.get("timestamp") != source_row["timestamp"].isoformat():
                failures.append(f"fold {index+1}: timestamp mismatch for {event_id}")
            if prediction.get("direction") != source_row["direction"]:
                failures.append(f"fold {index+1}: direction mismatch for {event_id}")
            if prediction.get("label") != source_row["label"]:
                failures.append(f"fold {index+1}: label mismatch for {event_id}")
            p = prediction.get("probability")
            if (
                not isinstance(p, (int, float))
                or isinstance(p, bool)
                or not math.isfinite(p)
                or not 0 <= p <= 1
            ):
                failures.append(f"fold {index+1}: invalid probability for {event_id}")
                continue
            same_direction = [r for r in train if r["direction"] == source_row["direction"]]
            if not same_direction:
                failures.append(
                    f"fold {index+1}: no prior history for direction {source_row['direction']}"
                )
                continue
            expected_probability = sum(r["label"] for r in same_direction) / len(same_direction)
            if float(p) != round(expected_probability, 12):
                failures.append(
                    f"fold {index+1}: probability mismatch for {event_id}; expected {round(expected_probability, 12)}, got {p}"
                )
            if prediction.get("method") not in (None, "direction_conditional"):
                failures.append(f"fold {index+1}: unexpected prediction method for {event_id}")
            fold_predictions.append(float(p))
            fold_labels.append(source_row["label"])
            fold_baseline.append(rate)
            actual_predictions.append((float(p), source_row["label"]))

        if len(fold_predictions) == len(expected["validation"]):
            expected_fold_model = _score(fold_predictions, fold_labels)
            expected_fold_baseline = _score(fold_baseline, fold_labels)
            if actual.get("model") != expected_fold_model:
                failures.append(f"fold {index+1}: model score does not recompute")
            if actual.get("baseline") != expected_fold_baseline:
                failures.append(f"fold {index+1}: baseline score does not recompute")

    expected_oos_ids = {row["event_id"] for fold in expected_folds for row in fold["validation"]}
    if seen_prediction_ids != expected_oos_ids:
        failures.append(
            "emitted prediction IDs do not exactly cover the reconstructed OOS validation set"
        )

    if actual_predictions:
        aggregate = result.get("aggregate") or {}
        expected_model = _score(
            [p for p, _ in actual_predictions], [y for _, y in actual_predictions]
        )
        expected_baseline_values: list[float] = []
        expected_baseline_labels: list[int] = []
        for fold in actual_folds[: len(expected_folds)]:
            rate = float(fold["training_outcome_rate"])
            for prediction in fold.get("predictions", []):
                label = prediction.get("label")
                if isinstance(label, bool) or not isinstance(label, int):
                    continue
                expected_baseline_values.append(rate)
                expected_baseline_labels.append(label)
        if expected_model != aggregate.get("model"):
            failures.append(
                "aggregate model score does not recompute from source-linked predictions"
            )
        if expected_baseline_values and _score(
            expected_baseline_values, expected_baseline_labels
        ) != aggregate.get("baseline"):
            failures.append("aggregate baseline score does not recompute")

    return {
        "status": "PASS" if not failures else "FAIL",
        "source_sha256": expected_source_hash,
        "result_artifact_sha256": hashlib.sha256(result_raw).hexdigest(),
        "source_complete_events": len(rows),
        "expected_folds": len(expected_folds),
        "actual_folds": len(actual_folds),
        "failures": failures,
        "checks": {
            "source_identity": not any("SHA-256" in f for f in failures),
            "dataset_identity": not any("dataset SHA-256" in f for f in failures),
            "contract_identity": not any("contract" in f for f in failures),
            "fold_membership": not any(
                "membership" in f or "events mismatch" in f for f in failures
            ),
            "embargo": not any("embargo" in f or "leakage" in f for f in failures),
            "source_linked_predictions": not any(
                "prediction event" in f
                or "timestamp mismatch" in f
                or "direction mismatch" in f
                or "label mismatch" in f
                for f in failures
            ),
            "probability_recomputation": not any("probability mismatch" in f for f in failures),
            "score_recomputation": not any("score does not recompute" in f for f in failures),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    output = audit(args.source, args.result)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
