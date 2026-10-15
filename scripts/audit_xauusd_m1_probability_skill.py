"""Audit probability skill, reliability, and temporal uncertainty for XAUUSD M1 OOS results.

Uses chronological walk-forward predictions and the disjoint final holdout.
Confidence intervals resample contiguous UTC calendar-day blocks to reduce the
IID assumption for overlapping 1-day outcomes. This is still a diagnostic, not
proof of tradable edge.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SOURCE = Path("artifacts/xauusd_m1_real_events_outcomes.json")
DEFAULT_RESULT = Path("artifacts/xauusd_m1_walkforward.json")
DEFAULT_CALIBRATION = Path("artifacts/xauusd_m1_oos_calibration_rerun.json")
DEFAULT_OUTPUT = Path("artifacts/xauusd_m1_probability_skill_audit.json")
BLOCK_LENGTHS_DAYS = (1, 3, 5)
BOOTSTRAP_REPLICATES = 5000


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must be timezone-aware: {value}")
    return parsed.astimezone(timezone.utc)


def _loss(probability: float, label: int) -> tuple[float, float]:
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("Probability must be finite and within [0, 1]")
    if label not in (0, 1):
        raise ValueError("Label must be binary")
    clipped = min(max(probability, 1e-15), 1.0 - 1e-15)
    return (probability - label) ** 2, -(
        label * math.log(clipped) + (1 - label) * math.log(1 - clipped)
    )


def _scores(rows: list[dict[str, Any]], probability_key: str) -> dict[str, float | int]:
    if not rows:
        raise ValueError("Cannot score an empty prediction set")
    losses = [_loss(float(row[probability_key]), int(row["label"])) for row in rows]
    return {
        "sample_count": len(rows),
        "brier_score": round(sum(item[0] for item in losses) / len(losses), 10),
        "log_loss": round(sum(item[1] for item in losses) / len(losses), 10),
        "observed_rate": round(sum(int(row["label"]) for row in rows) / len(rows), 10),
    }


def _reliability(
    rows: list[dict[str, Any]], probability_key: str, bins: int = 10
) -> list[dict[str, Any]]:
    output = []
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        selected = [
            row
            for row in rows
            if low <= float(row[probability_key]) < high
            or (index == bins - 1 and float(row[probability_key]) == 1.0)
        ]
        output.append(
            {
                "bin": index,
                "lower_inclusive": round(low, 4),
                "upper_exclusive": round(high, 4) if index < bins - 1 else None,
                "count": len(selected),
                "mean_predicted_probability": round(
                    sum(float(row[probability_key]) for row in selected) / len(selected), 8
                )
                if selected
                else None,
                "observed_positive_rate": round(
                    sum(int(row["label"]) for row in selected) / len(selected), 8
                )
                if selected
                else None,
            }
        )
    return output


def _block_bootstrap_delta(
    rows: list[dict[str, Any]],
    model_key: str,
    baseline_key: str,
    block_days: int,
    *,
    seed: int,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict[str, Any]:
    first = _time(min(row["timestamp"] for row in rows)).date()
    last = _time(max(row["timestamp"] for row in rows)).date()
    day_count = (last - first).days + 1
    if day_count < 2:
        return {
            "block_length_days": block_days,
            "calendar_days": day_count,
            "replicates": 0,
            "brier_delta_95ci": None,
            "log_loss_delta_95ci": None,
        }
    daily_stats: dict[str, list[float]] = {}
    for row in rows:
        day = _time(row["timestamp"]).date().isoformat()
        model_brier, model_log = _loss(float(row[model_key]), int(row["label"]))
        base_brier, base_log = _loss(float(row[baseline_key]), int(row["label"]))
        stats = daily_stats.setdefault(day, [0.0, 0.0, 0.0])
        stats[0] += model_brier - base_brier
        stats[1] += model_log - base_log
        stats[2] += 1.0
    days = [(first.fromordinal(first.toordinal() + i)).isoformat() for i in range(day_count)]
    day_stats = [daily_stats.get(day, [0.0, 0.0, 0.0]) for day in days]
    if day_count < block_days:
        block_days = day_count
    rng = random.Random(seed + block_days)
    brier_deltas: list[float] = []
    log_deltas: list[float] = []
    blocks_needed = math.ceil(day_count / block_days)
    for _ in range(replicates):
        total_brier = total_log = total_count = 0.0
        for _block in range(blocks_needed):
            start = rng.randrange(day_count)
            for offset in range(block_days):
                day_brier, day_log, day_count_events = day_stats[(start + offset) % day_count]
                total_brier += day_brier
                total_log += day_log
                total_count += day_count_events
        if total_count <= 0:
            continue
        brier_deltas.append(total_brier / total_count)
        log_deltas.append(total_log / total_count)

    def interval(values: list[float]) -> list[float] | None:
        if not values:
            return None
        values.sort()
        return [
            round(values[int(0.025 * (len(values) - 1))], 10),
            round(values[int(0.975 * (len(values) - 1))], 10),
        ]

    return {
        "block_length_days": block_days,
        "calendar_days": day_count,
        "replicates": len(brier_deltas),
        "delta_definition": "model minus baseline; negative favors model",
        "brier_delta_95ci": interval(brier_deltas),
        "log_loss_delta_95ci": interval(log_deltas),
    }


def _with_baseline(
    rows: list[dict[str, Any]], probability_key: str, baseline_probability: float
) -> list[dict[str, Any]]:
    return [
        {
            **row,
            probability_key: float(row[probability_key]),
            "baseline_probability": baseline_probability,
        }
        for row in rows
    ]


def audit(source_path: Path, result_path: Path, calibration_path: Path) -> dict[str, Any]:
    source_raw = source_path.read_bytes()
    result_raw = result_path.read_bytes()
    calibration_raw = calibration_path.read_bytes()
    source = json.loads(source_raw.decode("utf-8"))
    result = json.loads(result_raw.decode("utf-8"))
    calibration = json.loads(calibration_raw.decode("utf-8"))
    source_sha = _sha256_bytes(source_raw)
    result_sha = _sha256_bytes(result_raw)
    calibration_sha = _sha256_bytes(calibration_raw)
    if result.get("stage") != "M1_WALK_FORWARD_RAW_PROBABILITY":
        raise ValueError("Unexpected walk-forward result stage")
    if source.get("contract") != result.get("contract"):
        raise ValueError("Source and walk-forward contracts differ")
    if result.get("source_artifact", {}).get("sha256") != source_sha:
        raise ValueError("Walk-forward result is not bound to the supplied source SHA-256")
    if calibration.get("source_artifact", {}).get("sha256") != source_sha:
        raise ValueError("Calibration artifact is not bound to the supplied source SHA-256")
    if calibration.get("result_artifact", {}).get("sha256") != result_sha:
        raise ValueError("Calibration artifact is not bound to the supplied walk-forward SHA-256")

    validation: list[dict[str, Any]] = []
    for fold in result.get("folds", []):
        baseline_probability = float(fold["training_outcome_rate"])
        for prediction in fold.get("predictions", []):
            validation.append(
                {
                    "event_id": prediction["event_id"],
                    "timestamp": prediction["timestamp"],
                    "label": int(prediction["label"]),
                    "model_probability": float(prediction["probability"]),
                    "baseline_probability": baseline_probability,
                }
            )
    validation.sort(key=lambda row: (_time(row["timestamp"]), row["event_id"]))
    if len({row["event_id"] for row in validation}) != len(validation):
        raise ValueError("Duplicate walk-forward OOS event IDs")

    holdout = result.get("holdout", {})
    holdout_baseline = float(holdout["training_outcome_rate"])
    final_rows = [
        {
            "event_id": row["event_id"],
            "timestamp": row["timestamp"],
            "label": int(row["label"]),
            "model_probability": float(row["probability"]),
            "baseline_probability": holdout_baseline,
        }
        for row in holdout.get("predictions", [])
    ]
    if not validation or not final_rows:
        raise ValueError("Walk-forward validation and final holdout predictions are required")

    calibrated_rows = [
        {
            "event_id": row["event_id"],
            "timestamp": row["timestamp"],
            "label": int(row["label"]),
            "raw_probability": float(row["raw_probability"]),
            "calibrated_probability": float(row["calibrated_probability"]),
        }
        for row in calibration.get("predictions", [])
    ]
    if len({row["event_id"] for row in calibrated_rows}) != len(calibrated_rows):
        raise ValueError("Duplicate calibration event IDs")

    def comparison(
        rows: list[dict[str, Any]], model_key: str, baseline_key: str, seed: int
    ) -> dict[str, Any]:
        model_score = _scores(rows, model_key)
        baseline_score = _scores(rows, baseline_key)
        return {
            "model": model_score,
            "baseline": baseline_score,
            "delta_model_minus_baseline": {
                "brier_score": round(
                    model_score["brier_score"] - baseline_score["brier_score"], 10
                ),
                "log_loss": round(model_score["log_loss"] - baseline_score["log_loss"], 10),
            },
            "temporal_block_bootstrap": [
                _block_bootstrap_delta(rows, model_key, baseline_key, block_days, seed=seed)
                for block_days in BLOCK_LENGTHS_DAYS
            ],
            "model_reliability_10_bins": _reliability(rows, model_key),
            "baseline_reliability_10_bins": _reliability(rows, baseline_key),
        }

    calibration_comparison = {
        "raw": _scores(calibrated_rows, "raw_probability"),
        "calibrated": _scores(calibrated_rows, "calibrated_probability"),
        "delta_calibrated_minus_raw": {
            "brier_score": round(
                _scores(calibrated_rows, "calibrated_probability")["brier_score"]
                - _scores(calibrated_rows, "raw_probability")["brier_score"],
                10,
            ),
            "log_loss": round(
                _scores(calibrated_rows, "calibrated_probability")["log_loss"]
                - _scores(calibrated_rows, "raw_probability")["log_loss"],
                10,
            ),
        },
        "raw_reliability_10_bins": _reliability(calibrated_rows, "raw_probability"),
        "calibrated_reliability_10_bins": _reliability(calibrated_rows, "calibrated_probability"),
    }
    return {
        "schema": "xauusd-m1-probability-skill-audit.v1",
        "status": "COMPUTED_DIAGNOSTIC_NOT_EDGE_CERTIFICATION",
        "source_artifact": {"sha256": source_sha},
        "walkforward_artifact": {"sha256": result_sha},
        "calibration_artifact": {"sha256": calibration_sha},
        "methodology": {
            "baseline": "chronological training outcome rate, fixed before each validation/holdout window",
            "uncertainty": "circular moving-block bootstrap over UTC calendar days; block lengths 1, 3, and 5 days; 5,000 replicates each",
            "delta_sign": "model minus baseline; negative Brier/log-loss delta favors model",
            "limitations": [
                "bootstrap intervals are diagnostics and depend on block length",
                "calibration fit is causal expanding-window but has already shown degraded proper scores",
                "not a trading profitability test",
            ],
        },
        "walkforward_validation": comparison(
            validation, "model_probability", "baseline_probability", 20261015
        ),
        "final_holdout": comparison(
            final_rows, "model_probability", "baseline_probability", 20261016
        ),
        "causal_calibration_oos": calibration_comparison,
        "counts": {
            "walkforward_oos_predictions": len(validation),
            "final_holdout_predictions": len(final_rows),
            "causal_calibration_predictions": len(calibrated_rows),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = audit(args.source, args.result, args.calibration)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"status": report["status"], "counts": report["counts"], "output": str(args.output)},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
