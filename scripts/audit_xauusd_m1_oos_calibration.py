"""Independently audit the XAUUSD M1 OOS calibration artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path

MIN_SAMPLES = 10


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must be timezone-aware: {value}")
    return parsed.astimezone(timezone.utc)


def _pava(rows: list[tuple[float, int]]) -> tuple[tuple[float, float], ...]:
    """Match the production isotonic fit, including duplicate-x aggregation."""
    ordered = sorted(rows, key=lambda item: (item[0], item[1]))
    grouped: list[list[float | int]] = []
    for x, y in ordered:
        if grouped and float(grouped[-1][0]) == float(x):
            grouped[-1][1] = int(grouped[-1][1]) + 1
            grouped[-1][2] = int(grouped[-1][2]) + int(y)
        else:
            grouped.append([float(x), 1, int(y)])

    blocks: list[list[float | int]] = []
    for x, count, positives in grouped:
        blocks.append([x, float(positives) / int(count), int(count), int(positives)])
        while len(blocks) >= 2:
            a, b = blocks[-2], blocks[-1]
            if float(a[3]) / int(a[2]) <= float(b[3]) / int(b[2]):
                break
            blocks[-2:] = [
                [
                    min(float(a[0]), float(b[0])),
                    0.0,
                    int(a[2]) + int(b[2]),
                    float(a[3]) + float(b[3]),
                ]
            ]
    return tuple(
        (float(block[0]), round(max(0.0, min(1.0, float(block[3]) / int(block[2]))), 12))
        for block in blocks
    )


def _predict(breakpoints: tuple[tuple[float, float], ...], probability: float) -> float:
    xs = tuple(x for x, _ in breakpoints)
    return breakpoints[max(0, bisect_right(xs, probability) - 1)][1]


def _score(predictions: list[float], labels: list[int]) -> dict[str, float | int]:
    if not predictions or len(predictions) != len(labels):
        raise ValueError("Invalid score inputs")
    brier = sum((p - y) ** 2 for p, y in zip(predictions, labels)) / len(labels)
    log_loss = sum(
        -(
            y * math.log(min(max(p, 1e-15), 1.0 - 1e-15))
            + (1 - y) * math.log(1 - min(max(p, 1e-15), 1.0 - 1e-15))
        )
        for p, y in zip(predictions, labels)
    ) / len(labels)
    return {
        "sample_count": len(labels),
        "brier_score": round(brier, 10),
        "log_loss": round(log_loss, 10),
        "observed_rate": round(sum(labels) / len(labels), 10),
    }


def _source_rows(source: dict) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for event in source.get("events_data", []):
        outcome = event.get("outcome") or {}
        endpoint = (outcome.get("data_availability") or {}).get("realized_end_1d")
        label = outcome.get("hit_threshold_1d")
        event_id = event.get("event_id")
        if endpoint is None or label is None:
            continue
        if not isinstance(event_id, str) or not event_id or event_id in rows:
            raise ValueError(f"Invalid or duplicate source event_id: {event_id}")
        if not isinstance(label, bool):
            raise ValueError(f"Source outcome label must be boolean: {event_id}")
        timestamp = _time(event["timestamp"])
        realized_end = _time(endpoint)
        if realized_end <= timestamp:
            raise ValueError(f"Invalid realized_end: {event_id}")
        rows[event_id] = {"timestamp": timestamp, "realized_end": realized_end, "label": int(label)}
    return rows


def audit(source_path: Path, result_path: Path, calibration_path: Path) -> dict:
    source_raw = source_path.read_bytes()
    result_raw = result_path.read_bytes()
    calibration_raw = calibration_path.read_bytes()
    source = json.loads(source_raw.decode("utf-8"))
    result = json.loads(result_raw.decode("utf-8"))
    calibration = json.loads(calibration_raw.decode("utf-8"))
    failures: list[str] = []
    if calibration.get("stage") != "M1_OOS_ISOTONIC_CALIBRATION":
        failures.append("invalid calibration stage")
    if calibration.get("scientific_status") != "OOS_CALIBRATION_ONLY_NO_EDGE_CLAIM":
        failures.append("invalid scientific status")
    source_contract = source.get("contract")
    result_contract = result.get("contract")
    calibration_contract = calibration.get("contract")

    required_contract = {
        "asset": "XAUUSD",
        "timeframe": "M1",
        "label": "hit_threshold_1d",
    }
    if not isinstance(source_contract, dict):
        failures.append("invalid source contract")
    else:
        for key, expected in required_contract.items():
            if source_contract.get(key) != expected:
                failures.append(f"invalid source contract: {key}")

    if result_contract != source_contract or calibration_contract != source_contract:
        failures.append("contract mismatch")
    source_sha = hashlib.sha256(source_raw).hexdigest()
    result_sha = hashlib.sha256(result_raw).hexdigest()
    if calibration.get("source_artifact", {}).get("sha256") != source_sha:
        failures.append("source SHA mismatch")
    if calibration.get("result_artifact", {}).get("sha256") != result_sha:
        failures.append("result SHA mismatch")
    if result.get("source_artifact", {}).get("sha256") != source_sha:
        failures.append("result source SHA mismatch")

    source_rows = _source_rows(source)
    predictions: list[dict] = []
    seen: set[str] = set()
    for fold in result.get("folds", []):
        for prediction in fold.get("predictions", []):
            event_id = prediction.get("event_id")
            if event_id in seen or event_id not in source_rows:
                failures.append(f"invalid prediction membership: {event_id}")
                continue
            probability = prediction.get("probability")
            if (
                not isinstance(probability, (int, float))
                or not math.isfinite(float(probability))
                or not 0.0 <= float(probability) <= 1.0
            ):
                failures.append(f"invalid raw probability: {event_id}")
                continue
            source_row = source_rows[event_id]
            try:
                prediction_time = _time(prediction["timestamp"])
            except (KeyError, ValueError):
                failures.append(f"invalid prediction timestamp: {event_id}")
                continue
            if (
                prediction_time != source_row["timestamp"]
                or int(prediction.get("label", -1)) != source_row["label"]
            ):
                failures.append(f"prediction/source mismatch: {event_id}")
                continue
            predictions.append(
                {
                    "event_id": event_id,
                    "timestamp": prediction_time,
                    "probability": float(probability),
                    "label": source_row["label"],
                    "realized_end": source_row["realized_end"],
                }
            )
            seen.add(event_id)
    predictions.sort(key=lambda row: (row["timestamp"], row["event_id"]))

    metadata = calibration.get("calibration", {})
    refit_interval = metadata.get("refit_interval")
    if not isinstance(refit_interval, int) or refit_interval < 1:
        failures.append("invalid refit interval metadata")
        refit_interval = 1
    if metadata.get("minimum_prior_samples") != MIN_SAMPLES:
        failures.append("minimum prior sample metadata mismatch")
    if metadata.get("total_oos_predictions") != len(predictions):
        failures.append("total OOS prediction count mismatch")

    completion_order = sorted(
        range(len(predictions)),
        key=lambda index: (predictions[index]["realized_end"], predictions[index]["event_id"]),
    )
    completion_cursor = 0
    eligible_indices: list[int] = []
    expected: list[dict] = []
    raw_scores: list[float] = []
    calibrated_scores: list[float] = []
    labels: list[int] = []
    fit_summaries: list[dict] = []
    breakpoints: tuple[tuple[float, float], ...] | None = None
    last_fit_eligible_count = -1
    fit_id = 0
    fit_cutoff_timestamp: datetime | None = None
    warmup_count = 0
    refit_count = 0

    for row in predictions:
        while completion_cursor < len(completion_order):
            completed_index = completion_order[completion_cursor]
            completed = predictions[completed_index]
            if completed["realized_end"] >= row["timestamp"]:
                break
            eligible_indices.append(completed_index)
            completion_cursor += 1

        prior = [predictions[index] for index in eligible_indices]
        classes = {item["label"] for item in prior}
        if len(prior) < MIN_SAMPLES or classes != {0, 1}:
            warmup_count += 1
            continue

        should_refit = breakpoints is None or len(prior) - last_fit_eligible_count >= refit_interval
        if should_refit:
            breakpoints = _pava([(item["probability"], item["label"]) for item in prior])
            last_fit_eligible_count = len(prior)
            refit_count += 1
            fit_id += 1
            fit_cutoff_timestamp = row["timestamp"]
            fit_summaries.append(
                {
                    "fit_id": fit_id,
                    "fit_cutoff_timestamp": row["timestamp"].isoformat(),
                    "training_event_count": len(prior),
                    "training_positive_count": sum(item["label"] for item in prior),
                    "training_negative_count": sum(1 - item["label"] for item in prior),
                }
            )

        calibrated = _predict(breakpoints, row["probability"])
        raw_scores.append(row["probability"])
        calibrated_scores.append(calibrated)
        labels.append(row["label"])
        expected.append(
            {
                "event_id": row["event_id"],
                "timestamp": row["timestamp"].isoformat(),
                "raw_probability": round(row["probability"], 12),
                "calibrated_probability": round(calibrated, 12),
                "label": row["label"],
                "calibration_fit_id": fit_id,
                "calibration_fit_cutoff_timestamp": fit_cutoff_timestamp.isoformat()
                if fit_cutoff_timestamp
                else None,
                "calibration_training_event_count": len(prior),
            }
        )

    if calibration.get("predictions") != expected:
        failures.append("calibration predictions differ from independent reconstruction")
    expected_raw_score = _score(raw_scores, labels) if raw_scores else None
    expected_calibrated_score = _score(calibrated_scores, labels) if calibrated_scores else None
    if calibration.get("raw_score") != expected_raw_score:
        failures.append("raw score differs from independent reconstruction")
    if calibration.get("calibrated_score") != expected_calibrated_score:
        failures.append("calibrated score differs from independent reconstruction")
    if metadata.get("eligible_oos_predictions") != len(expected):
        failures.append("eligible OOS prediction count mismatch")
    if metadata.get("warmup_excluded_predictions") != warmup_count:
        failures.append("warmup count mismatch")
    if metadata.get("refit_count") != refit_count:
        failures.append("refit count mismatch")
    if metadata.get("fit_summaries") != fit_summaries:
        failures.append("fit summaries differ from independent reconstruction")
    for record in calibration.get("predictions", []):
        probability = record.get("calibrated_probability")
        if (
            not isinstance(probability, (int, float))
            or not math.isfinite(float(probability))
            or not 0.0 <= float(probability) <= 1.0
        ):
            failures.append(f"invalid calibrated probability: {record.get('event_id')}")

    return {
        "status": "PASS" if not failures else "FAIL",
        "stage": "M1_OOS_ISOTONIC_CALIBRATION_INDEPENDENT_AUDIT",
        "source_sha256": source_sha,
        "result_sha256": result_sha,
        "calibration_sha256": hashlib.sha256(calibration_raw).hexdigest(),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("calibration", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/xauusd_m1_oos_calibration_audit.json")
    )
    args = parser.parse_args()
    report = audit(args.source, args.result, args.calibration)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
