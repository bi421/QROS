"""Expanding-window, label-overlap-purged validation for chronological classifiers.

Rows must be sorted chronologically and contain timestamp and label_end_timestamp
ISO strings plus the logistic model's features and binary label. A training event is
purged when its outcome window reaches or crosses the validation start.
"""

from __future__ import annotations

import math
from typing import Any

from researchos.orchestration.logistic_probability import fit_evaluate_logistic


def purged_walk_forward_evaluate(
    rows: list[dict[str, Any]],
    *,
    n_splits: int = 4,
    min_train_rows: int = 100,
    l2: float = 1.0,
) -> dict[str, Any]:
    """Run expanding chronological folds, purging overlapping training labels.

    Each fold uses only rows strictly earlier than its validation start whose
    label_end_timestamp is also strictly earlier than that start. The function
    reports per-fold metrics; it does not claim independence across folds.
    """
    if n_splits < 2 or min_train_rows < 20 or not math.isfinite(l2) or l2 < 0:
        raise ValueError("n_splits >= 2, min_train_rows >= 20, and finite l2 >= 0 required")
    if any(
        not isinstance(row.get("timestamp"), str)
        or not isinstance(row.get("label_end_timestamp"), str)
        for row in rows
    ):
        raise ValueError("every row requires ISO timestamp and label_end_timestamp strings")
    ordered = list(rows)
    if any(ordered[i]["timestamp"] >= ordered[i + 1]["timestamp"] for i in range(len(ordered) - 1)):
        raise ValueError(
            "event timestamps must be strictly increasing and unique; refusing to reorder source rows"
        )
    if not ordered:
        return {"status": "INSUFFICIENT_DATA", "folds": [], "n_events": 0}

    test_size = len(ordered) // (n_splits + 1)
    initial_train_size = len(ordered) - test_size * n_splits
    if test_size < 1 or initial_train_size < min_train_rows:
        return {
            "status": "INSUFFICIENT_DATA",
            "folds": [],
            "n_events": len(ordered),
            "initial_train_size": initial_train_size,
            "test_size": test_size,
        }

    folds = []
    for fold_index in range(n_splits):
        test_start_index = initial_train_size + fold_index * test_size
        test_end_index = test_start_index + test_size
        test_rows = ordered[test_start_index:test_end_index]
        validation_start = test_rows[0]["timestamp"]
        candidate_train = ordered[:test_start_index]
        train_rows = [
            row for row in candidate_train if row["label_end_timestamp"] < validation_start
        ]
        purged = len(candidate_train) - len(train_rows)
        if len(train_rows) < min_train_rows:
            folds.append(
                {
                    "fold": fold_index + 1,
                    "status": "INSUFFICIENT_TRAIN_AFTER_PURGE",
                    "train_n": len(train_rows),
                    "test_n": len(test_rows),
                    "purged_n": purged,
                    "validation_start": validation_start,
                }
            )
            continue
        result = fit_evaluate_logistic(train_rows, test_rows, l2=l2)
        folds.append(
            {
                "fold": fold_index + 1,
                "status": result["status"],
                "train_n": len(train_rows),
                "test_n": len(test_rows),
                "purged_n": purged,
                "validation_start": validation_start,
                "validation_end": test_rows[-1]["timestamp"],
                "holdout_metrics": result.get("holdout_metrics"),
                "train_prevalence_baseline_metrics": result.get(
                    "holdout_train_prevalence_baseline_metrics"
                ),
            }
        )
    valid = [
        f
        for f in folds
        if f.get("status") == "FITTED_TRAIN_EVALUATED_HOLDOUT" and f.get("holdout_metrics")
    ]
    summary = {}
    for metric in ("log_loss", "brier_score", "expected_calibration_error_10_bins"):
        values = [f["holdout_metrics"][metric] for f in valid]
        baseline = [f["train_prevalence_baseline_metrics"][metric] for f in valid]
        summary[metric] = {
            "mean": sum(values) / len(values) if values else None,
            "baseline_mean": sum(baseline) / len(baseline) if baseline else None,
            "folds": len(values),
        }
    return {
        "status": "COMPLETED" if valid else "INSUFFICIENT_VALID_FOLDS",
        "method": "expanding-window walk-forward; training rows purged when label_end_timestamp >= validation start",
        "n_events": len(ordered),
        "n_splits_requested": n_splits,
        "valid_folds": len(valid),
        "folds": folds,
        "mean_metrics": summary,
        "warning": "Fold metrics are chronological diagnostics, not proof of profitability; labels may overlap within validation folds and economic costs must be tested separately.",
    }


__all__ = ["purged_walk_forward_evaluate"]
