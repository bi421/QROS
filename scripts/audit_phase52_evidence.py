"""Independent structural and metric auditor for Phase 5.2 evidence artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from researchos.experiments.phase51.statistics import confidence_interval_diff, evaluate_significance

FEATURE_SET_NAMES = (
    "PRICE_ONLY",
    "PRICE + DXY",
    "PRICE + US10Y",
    "PRICE + VIX",
    "PRICE + ALL",
)
REQUIRED_SOURCES = ("XAUUSD", "DXY", "US10Y", "VIX")


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _close(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)


def _configuration_hash(configuration: object) -> str:
    if not isinstance(configuration, dict):
        raise ValueError("configuration is missing")
    canonical = json.dumps(configuration, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _model_brier(records: list[dict]) -> float:
    total = 0.0
    for record in records:
        label = int(record["label"])
        probabilities = record["probabilities"]
        total += sum(
            (float(probabilities[str(cls)]) - (1.0 if cls == label else 0.0)) ** 2
            for cls in (-1, 0, 1)
        )
    return total / len(records) / 3.0


def _baseline_brier(records: list[dict], baseline_prediction: int) -> float:
    total = 0.0
    for record in records:
        label = int(record["label"])
        total += sum(
            (
                (1.0 if cls == baseline_prediction else 0.0)
                - (1.0 if cls == label else 0.0)
            )
            ** 2
            for cls in (-1, 0, 1)
        )
    return total / len(records) / 3.0


def audit(path: Path) -> dict[str, object]:
    failures: list[str] = []
    payload = json.loads(path.read_text(encoding="utf-8"))

    if payload.get("schema") != "researchos/phase52/evidence/v3":
        failures.append("unexpected or missing evidence schema")
    repository_commit = payload.get("repository_commit")
    if (
        not isinstance(repository_commit, str)
        or len(repository_commit) != 40
        or any(c not in "0123456789abcdefABCDEF" for c in repository_commit)
    ):
        failures.append("repository_commit is not an exact 40-character Git SHA")

    configuration = payload.get("configuration")
    expected_config_hash = _configuration_hash(configuration)
    if payload.get("configuration_hash") != expected_config_hash:
        failures.append("configuration hash does not recompute")

    if payload.get("feature_set_scope") != list(FEATURE_SET_NAMES):
        failures.append("feature-set search scope is missing or changed")
    holdout_contract = payload.get("holdout_contract")
    if not isinstance(holdout_contract, dict) or any(
        holdout_contract.get(key) is not True
        for key in (
            "wfo_aggregate_excludes_holdout",
            "selection_excludes_holdout",
            "calibration_excludes_holdout",
        )
    ):
        failures.append("top-level holdout exclusion contract is missing")

    sources = payload.get("sources")
    if not isinstance(sources, dict):
        failures.append("source identities are missing")
    else:
        for source in REQUIRED_SOURCES:
            entry = sources.get(source)
            if not isinstance(entry, dict):
                failures.append(f"source identity missing: {source}")
                continue
            value = entry.get("sha256")
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)
            ):
                failures.append(f"invalid source SHA-256: {source}")

    common = payload.get("common_sample")
    holdout_size = configuration.get("holdout_size") if isinstance(configuration, dict) else None
    train_size = configuration.get("train_size") if isinstance(configuration, dict) else None
    validation_size = configuration.get("validation_size") if isinstance(configuration, dict) else None
    horizon = configuration.get("horizon") if isinstance(configuration, dict) else None
    if not all(isinstance(v, int) and v > 0 for v in (holdout_size, train_size, validation_size, horizon)):
        failures.append("configuration sample sizes/horizon are invalid")
    elif not isinstance(common, dict) or int(common.get("count", 0)) < train_size + validation_size + holdout_size + horizon:
        failures.append("common sample is too small for the declared holdout protocol")

    results = payload.get("results")
    if not isinstance(results, dict):
        failures.append("feature-set results are missing")
        results = {}

    checked_results = 0
    for feature_set in FEATURE_SET_NAMES:
        result = results.get(feature_set)
        if not isinstance(result, dict):
            failures.append(f"{feature_set}: result missing")
            continue
        metadata = result.get("metadata")
        if not isinstance(metadata, dict):
            failures.append(f"{feature_set}: metadata missing")
            continue
        checked_results += 1

        if metadata.get("feature_set") != feature_set:
            failures.append(f"{feature_set}: feature-set identity mismatch")
        if metadata.get("feature_set_search_scope") != list(FEATURE_SET_NAMES):
            failures.append(f"{feature_set}: feature-set search scope mismatch")
        if metadata.get("holdout_used_for_feature_selection") is not False:
            failures.append(f"{feature_set}: holdout selection exclusion missing")

        temporal = metadata.get("temporal_contract")
        if not isinstance(temporal, dict):
            failures.append(f"{feature_set}: temporal contract missing")
        else:
            for key in (
                "feature_availability_convention",
                "label_definition",
                "walk_forward_training_rule",
                "final_holdout_training_rule",
            ):
                if not isinstance(temporal.get(key), str) or not temporal.get(key):
                    failures.append(f"{feature_set}: temporal contract field missing: {key}")
            if temporal.get("holdout_is_chronologically_disjoint") is not True:
                failures.append(f"{feature_set}: holdout disjointness contract invalid")
            if temporal.get("holdout_excluded_from_wfo_aggregate") is not True:
                failures.append(f"{feature_set}: holdout aggregate exclusion missing")

        calibration = metadata.get("calibration_contract")
        if not isinstance(calibration, dict):
            failures.append(f"{feature_set}: calibration contract missing")
        else:
            if calibration.get("parameter_fitting_performed") is not False:
                failures.append(f"{feature_set}: calibration fitting contract invalid")
            if calibration.get("holdout_excluded") is not True:
                failures.append(f"{feature_set}: holdout calibration exclusion invalid")
            if calibration.get("training_population") != "walk-forward validation predictions only":
                failures.append(f"{feature_set}: unexpected calibration population")

        folds = metadata.get("wfo_folds")
        if not isinstance(folds, list) or not folds:
            failures.append(f"{feature_set}: WFO fold boundary ledger missing")
        else:
            prior_validation_end: datetime | None = None
            for fold in folds:
                if not isinstance(fold, dict):
                    failures.append(f"{feature_set}: invalid WFO fold record")
                    continue
                try:
                    _timestamp(fold["training_end"])
                    training_realized_end = _timestamp(fold["training_max_realized_end"])
                    validation_start = _timestamp(fold["validation_start"])
                    validation_end = _timestamp(fold["validation_end"])
                    validation_realized_end = _timestamp(fold["validation_realized_end"])
                except (KeyError, ValueError, TypeError) as exc:
                    failures.append(f"{feature_set}: invalid WFO temporal boundary: {exc}")
                    continue
                if not training_realized_end < validation_start:
                    failures.append(f"{feature_set}: WFO training realized-end crosses validation start")
                if validation_end < validation_start:
                    failures.append(f"{feature_set}: WFO validation interval is reversed")
                if not validation_realized_end >= validation_end:
                    failures.append(f"{feature_set}: validation realized-end precedes validation end")
                if prior_validation_end is not None and validation_start <= prior_validation_end:
                    failures.append(f"{feature_set}: validation windows overlap")
                prior_validation_end = validation_end

        holdout = metadata.get("holdout")
        if not isinstance(holdout, dict):
            failures.append(f"{feature_set}: final holdout artifact missing")
            continue
        if holdout.get("holdout_events") != holdout_size:
            failures.append(f"{feature_set}: holdout size mismatch")
        predictions = holdout.get("predictions")
        if not isinstance(predictions, list) or len(predictions) != holdout_size:
            failures.append(f"{feature_set}: holdout prediction count mismatch")
            continue
        try:
            holdout_start = _timestamp(holdout["start"])
            holdout_end = _timestamp(holdout["end"])
            terminal_realized_end = _timestamp(holdout["terminal_realized_end"])
            training_max_realized_end = _timestamp(holdout["training_max_realized_end"])
        except (KeyError, ValueError, TypeError) as exc:
            failures.append(f"{feature_set}: invalid holdout boundary: {exc}")
            continue
        if holdout_end < holdout_start:
            failures.append(f"{feature_set}: holdout interval reversed")
        if training_max_realized_end >= holdout_start:
            failures.append(f"{feature_set}: holdout training crosses holdout start")
        if holdout.get("fit_is_pre_holdout_only") is not True:
            failures.append(f"{feature_set}: holdout fit boundary contract invalid")
        if holdout.get("selection_frozen_before_scoring") is not True:
            failures.append(f"{feature_set}: selection freeze contract missing")
        if holdout.get("holdout_used_for_selection") is not False:
            failures.append(f"{feature_set}: holdout used for selection")
        if terminal_realized_end < holdout_end:
            failures.append(f"{feature_set}: terminal realized-end precedes holdout end")

        if folds:
            last_validation_end = _timestamp(folds[-1]["validation_end"])
            if last_validation_end >= holdout_start:
                failures.append(f"{feature_set}: holdout overlaps last WFO validation boundary")

        seen_timestamps: set[str] = set()
        for prediction in predictions:
            if not isinstance(prediction, dict):
                failures.append(f"{feature_set}: malformed holdout prediction record")
                continue
            try:
                timestamp = _timestamp(prediction["timestamp"])
                realized_end = _timestamp(prediction["realized_end"])
                label = int(prediction["label"])
                predicted = int(prediction["prediction"])
                probabilities = prediction["probabilities"]
            except (KeyError, ValueError, TypeError) as exc:
                failures.append(f"{feature_set}: malformed holdout prediction: {exc}")
                continue
            if not holdout_start <= timestamp <= holdout_end:
                failures.append(f"{feature_set}: holdout prediction outside holdout interval")
            if realized_end < timestamp:
                failures.append(f"{feature_set}: realized-end precedes prediction timestamp")
            if timestamp.isoformat() in seen_timestamps:
                failures.append(f"{feature_set}: duplicate holdout prediction timestamp")
            seen_timestamps.add(timestamp.isoformat())
            if predicted not in (-1, 0, 1) or label not in (-1, 0, 1):
                failures.append(f"{feature_set}: invalid holdout class value")
            if not isinstance(probabilities, dict):
                failures.append(f"{feature_set}: holdout probabilities missing")
                continue
            try:
                values = [float(probabilities[str(cls)]) for cls in (-1, 0, 1)]
            except (KeyError, ValueError, TypeError) as exc:
                failures.append(f"{feature_set}: invalid holdout probabilities: {exc}")
                continue
            if any(not math.isfinite(v) or v < 0.0 for v in values):
                failures.append(f"{feature_set}: non-finite/negative holdout probability")
            if not _close(sum(values), 1.0):
                failures.append(f"{feature_set}: holdout probability mass does not sum to one")

        if holdout.get("model") and predictions:
            expected_model_brier = _model_brier(predictions)
            actual_model_brier = holdout["model"].get("brier_score") if isinstance(holdout["model"], dict) else None
            if actual_model_brier is None or not _close(expected_model_brier, float(actual_model_brier)):
                failures.append(f"{feature_set}: holdout model Brier does not recompute")
            predicted_accuracy = (
                sum(int(row["prediction"]) == int(row["label"]) for row in predictions) / len(predictions)
            )
            actual_accuracy = holdout["model"].get("accuracy") if isinstance(holdout["model"], dict) else None
            if actual_accuracy is None or not _close(predicted_accuracy, float(actual_accuracy)):
                failures.append(f"{feature_set}: holdout model accuracy does not recompute")
        else:
            failures.append(f"{feature_set}: holdout model score missing")

        baseline_prediction = holdout.get("baseline_prediction")
        if not isinstance(baseline_prediction, int) or baseline_prediction not in (-1, 0, 1):
            failures.append(f"{feature_set}: holdout baseline prediction missing")
        elif isinstance(holdout.get("baseline"), dict) and predictions:
            expected_baseline_brier = _baseline_brier(predictions, baseline_prediction)
            actual_baseline_brier = holdout["baseline"].get("brier_score")
            if actual_baseline_brier is None or not _close(expected_baseline_brier, float(actual_baseline_brier)):
                failures.append(f"{feature_set}: holdout baseline Brier does not recompute")
            predicted_accuracy = (
                sum(baseline_prediction == int(row["label"]) for row in predictions) / len(predictions)
            )
            actual_accuracy = holdout["baseline"].get("accuracy")
            if actual_accuracy is None or not _close(predicted_accuracy, float(actual_accuracy)):
                failures.append(f"{feature_set}: holdout baseline accuracy does not recompute")
        else:
            failures.append(f"{feature_set}: holdout baseline score missing")

        significance = holdout.get("significance")
        if not isinstance(significance, dict):
            failures.append(f"{feature_set}: holdout significance missing")
        else:
            recomputed_significance = evaluate_significance(
                [int(row["prediction"]) for row in predictions],
                [baseline_prediction] * len(predictions),
                [int(row["label"]) for row in predictions],
            ).to_dict()
            for key in ("p_value", "model_better_count", "baseline_better_count"):
                if key not in significance or not _close(float(significance[key]), float(recomputed_significance[key])):
                    failures.append(f"{feature_set}: holdout significance {key} does not recompute")

        ci = holdout.get("accuracy_delta_ci_95")
        if (
            not isinstance(ci, dict)
            or not isinstance(ci.get("lower"), (int, float))
            or not isinstance(ci.get("upper"), (int, float))
            or float(ci["lower"]) > float(ci["upper"])
        ):
            failures.append(f"{feature_set}: holdout uncertainty interval missing or invalid")
        else:
            recomputed_ci = confidence_interval_diff(
                [
                    float(int(row["prediction"]) == int(row["label"]))
                    for row in predictions
                ],
                [
                    float(baseline_prediction == int(row["label"]))
                    for row in predictions
                ],
            )
            if not _close(float(ci["lower"]), recomputed_ci[0]) or not _close(
                float(ci["upper"]), recomputed_ci[1]
            ):
                failures.append(f"{feature_set}: holdout uncertainty interval does not recompute")

    return {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "checked_feature_sets": checked_results,
        "holdout_size": holdout_size,
    }


def main(argv: list[str] | None = None) -> int:
    if not argv:
        argv = sys.argv[1:]
    if len(argv) != 1:
        print("usage: python scripts/audit_phase52_evidence.py <phase52_evidence.json>")
        return 2
    result = audit(Path(argv[0]))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
