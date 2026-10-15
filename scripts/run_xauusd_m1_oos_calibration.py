"""Calibrate XAUUSD M1 walk-forward probabilities using prior OOS outcomes only.

This stage is deliberately separate from the in-sample ProbabilityCalibrator.
Each validation prediction is calibrated only from earlier OOS predictions whose
realized outcome endpoint is strictly before the prediction timestamp.

Calibration is fit with a causal expanding window and periodic refits. Reusing a
mapping between refits is safe because the mapping was fitted only from outcomes
that were already realized before the fit timestamp.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path

MIN_SAMPLES = 10
REFIT_INTERVAL = 250
REQUIRED_CONTRACT = {"asset": "XAUUSD", "timeframe": "M1", "label": "hit_threshold_1d"}


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must be timezone-aware: {value}")
    return parsed.astimezone(timezone.utc)


def _pava(rows: list[tuple[float, int]]) -> tuple[tuple[float, float], ...]:
    """Fit isotonic regression after aggregating duplicate x values.

    Duplicate probabilities must be one weighted observation at a single x.
    Keeping separate 0/1 blocks at the same x can make bisect_right select an
    arbitrary extreme block, producing spurious 0/1 calibrated probabilities.
    """
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
    index = bisect_right(xs, probability) - 1
    if index < 0:
        index = 0
    return breakpoints[index][1]


def _score(predictions: list[float], labels: list[int]) -> dict[str, float | int]:
    if not predictions or len(predictions) != len(labels):
        raise ValueError("Predictions and labels must be non-empty and aligned")
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


def _source_rows(source: dict) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for event in source.get("events_data", []):
        event_id = event.get("event_id")
        outcome = event.get("outcome") or {}
        endpoint = (outcome.get("data_availability") or {}).get("realized_end_1d")
        label = outcome.get("hit_threshold_1d")
        if endpoint is None or label is None:
            continue
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("Complete source event requires event_id")
        if event_id in rows:
            raise ValueError(f"Duplicate source event_id: {event_id}")
        if not isinstance(label, bool):
            raise ValueError(f"Source outcome label must be boolean: {event_id}")
        timestamp = _time(event["timestamp"])
        realized_end = _time(endpoint)
        if realized_end <= timestamp:
            raise ValueError(f"Source realized_end must be after event timestamp: {event_id}")
        rows[event_id] = {
            "timestamp": timestamp,
            "realized_end": realized_end,
            "label": int(label),
            "direction": event.get("direction"),
        }
    return rows


def run(
    source_path: Path,
    result_path: Path,
    output_path: Path,
    refit_interval: int = REFIT_INTERVAL,
) -> dict:
    if refit_interval < 1:
        raise ValueError("refit_interval must be >= 1")
    source_raw = source_path.read_bytes()
    result_raw = result_path.read_bytes()
    source = json.loads(source_raw.decode("utf-8"))
    result = json.loads(result_raw.decode("utf-8"))
    if result.get("stage") != "M1_WALK_FORWARD_RAW_PROBABILITY":
        raise ValueError("Input result is not the required walk-forward stage")
    source_contract = source.get("contract", {})
    result_contract = result.get("contract", {})
    if source_contract != result_contract:
        raise ValueError("Source and result contracts differ")
    if any(source_contract.get(key) != value for key, value in REQUIRED_CONTRACT.items()):
        raise ValueError("Unexpected XAUUSD M1 contract")
    if result.get("source_artifact", {}).get("sha256") != hashlib.sha256(source_raw).hexdigest():
        raise ValueError("Result source artifact SHA-256 does not match supplied source")

    source_rows = _source_rows(source)
    predictions: list[dict] = []
    seen: set[str] = set()
    for fold in result.get("folds", []):
        for prediction in fold.get("predictions", []):
            event_id = prediction.get("event_id")
            if event_id in seen:
                raise ValueError(f"Duplicate OOS prediction event_id: {event_id}")
            if event_id not in source_rows:
                raise ValueError(f"Prediction event is missing from source: {event_id}")
            if not isinstance(prediction.get("probability"), (int, float)):
                raise ValueError(f"Invalid probability: {event_id}")
            p = float(prediction["probability"])
            if not math.isfinite(p) or not 0.0 <= p <= 1.0:
                raise ValueError(f"Probability outside [0,1]: {event_id}")
            source_row = source_rows[event_id]
            if source_row["timestamp"] != _time(prediction["timestamp"]):
                raise ValueError(f"Prediction timestamp differs from source: {event_id}")
            if source_row["label"] != int(prediction["label"]):
                raise ValueError(f"Prediction label differs from source: {event_id}")
            predictions.append(
                {
                    "event_id": event_id,
                    "timestamp": source_row["timestamp"],
                    "probability": p,
                    "label": source_row["label"],
                    "realized_end": source_row["realized_end"],
                }
            )
            seen.add(event_id)

    predictions.sort(key=lambda row: (row["timestamp"], row["event_id"]))
    if len(predictions) < MIN_SAMPLES + 1:
        raise ValueError("At least 11 OOS predictions are required for leakage-safe calibration")

    completion_order = sorted(
        range(len(predictions)),
        key=lambda index: (predictions[index]["realized_end"], predictions[index]["event_id"]),
    )
    completion_cursor = 0
    eligible_indices: list[int] = []

    calibrated: list[float] = []
    raw_eligible: list[float] = []
    labels: list[int] = []
    records: list[dict] = []
    fit_summaries: list[dict] = []
    warmup_count = 0
    refit_count = 0
    last_fit_eligible_count = -1
    breakpoints: tuple[tuple[float, float], ...] | None = None
    fit_id = 0
    fit_cutoff_timestamp: datetime | None = None

    for row in predictions:
        while completion_cursor < len(completion_order):
            completed_index = completion_order[completion_cursor]
            completed = predictions[completed_index]
            if completed["realized_end"] >= row["timestamp"]:
                break
            eligible_indices.append(completed_index)
            completion_cursor += 1

        prior = [predictions[item] for item in eligible_indices]
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

        if breakpoints is None:
            raise RuntimeError("Calibration breakpoints are missing after refit")
        calibrated_probability = _predict(breakpoints, row["probability"])
        raw_eligible.append(row["probability"])
        calibrated.append(calibrated_probability)
        labels.append(row["label"])
        records.append(
            {
                "event_id": row["event_id"],
                "timestamp": row["timestamp"].isoformat(),
                "raw_probability": round(row["probability"], 12),
                "calibrated_probability": round(calibrated_probability, 12),
                "label": row["label"],
                "calibration_fit_id": fit_id,
                "calibration_fit_cutoff_timestamp": fit_cutoff_timestamp.isoformat()
                if fit_cutoff_timestamp
                else None,
                "calibration_training_event_count": len(prior),
            }
        )

    if len(records) < 1:
        raise ValueError("No OOS predictions have sufficient leakage-safe calibration history")

    raw_score = _score(raw_eligible, labels)
    calibrated_score = _score(calibrated, labels)
    if (
        calibrated_score["brier_score"] > raw_score["brier_score"]
        or calibrated_score["log_loss"] > raw_score["log_loss"]
    ):
        scoring_status = "DEGRADED"
    elif (
        calibrated_score["brier_score"] < raw_score["brier_score"]
        and calibrated_score["log_loss"] < raw_score["log_loss"]
    ):
        scoring_status = "IMPROVED"
    else:
        scoring_status = "NO_CLEAR_IMPROVEMENT"

    output = {
        "stage": "M1_OOS_ISOTONIC_CALIBRATION",
        "scientific_status": "OOS_CALIBRATION_ONLY_NO_EDGE_CLAIM",
        "source_artifact": {
            "path": str(source_path),
            "sha256": hashlib.sha256(source_raw).hexdigest(),
        },
        "result_artifact": {
            "path": str(result_path),
            "sha256": hashlib.sha256(result_raw).hexdigest(),
        },
        "contract": result_contract,
        "calibration": {
            "method": "isotonic_pava",
            "minimum_prior_samples": MIN_SAMPLES,
            "refit_interval": refit_interval,
            "refit_policy": "causal_expanding_window_periodic_refit",
            "fit_uses_current_validation_label": False,
            "fit_uses_future_outcomes": False,
            "temporal_rule": "training realized_end < calibration fit/current validation timestamp",
            "total_oos_predictions": len(predictions),
            "eligible_oos_predictions": len(records),
            "warmup_excluded_predictions": warmup_count,
            "refit_count": refit_count,
            "fit_summaries": fit_summaries,
        },
        "raw_score": raw_score,
        "calibrated_score": calibrated_score,
        "scoring_assessment": {
            "status": scoring_status,
            "brier_delta_calibrated_minus_raw": round(
                float(calibrated_score["brier_score"]) - float(raw_score["brier_score"]), 10
            ),
            "log_loss_delta_calibrated_minus_raw": round(
                float(calibrated_score["log_loss"]) - float(raw_score["log_loss"]), 10
            ),
            "downstream_use": (
                "BLOCK_CALIBRATED_PROBABILITIES"
                if scoring_status != "IMPROVED"
                else "REQUIRES_SEPARATE_HOLDOUT_REVIEW"
            ),
        },
        "predictions": records,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/xauusd_m1_oos_calibration.json")
    )
    parser.add_argument("--refit-interval", type=int, default=REFIT_INTERVAL)
    args = parser.parse_args()
    output = run(args.source, args.result, args.output, args.refit_interval)
    print(f"OOS samples: {len(output['predictions'])}")
    print(f"Raw Brier: {output['raw_score']['brier_score']}")
    print(f"Calibrated Brier: {output['calibrated_score']['brier_score']}")
    print(f"Refits: {output['calibration']['refit_count']}")
    print(f"Artifact: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
