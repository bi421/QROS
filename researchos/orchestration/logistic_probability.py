"""Small, deterministic NumPy logistic model for chronological research validation.

This is a research baseline, not an execution signal. Fit only on training data;
report holdout log loss and Brier score. L2 regularization stabilizes coefficients.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

FEATURES = ("z_speed", "body_ratio", "upper_wick_ratio", "lower_wick_ratio", "h1_aligned")


def fit_evaluate_logistic(
    train_rows: list[dict[str, Any]],
    holdout_rows: list[dict[str, Any]],
    *,
    l2: float = 1.0,
    max_iter: int = 100,
    tolerance: float = 1e-8,
) -> dict[str, Any]:
    """Fit L2 logistic regression on TRAIN rows and evaluate untouched HOLDOUT rows.

    Each row contains the five FEATURE keys and integer ``label`` (1 continuation,
    0 reversal). Callers should exclude sideways outcomes before passing rows.
    """
    if not math.isfinite(l2) or l2 < 0 or max_iter < 1:
        raise ValueError("l2 must be finite and >= 0; max_iter must be >= 1")
    if len(train_rows) < 20 or len(holdout_rows) < 1:
        return {
            "status": "INSUFFICIENT_DATA",
            "train_n": len(train_rows),
            "holdout_n": len(holdout_rows),
        }

    def matrix(rows):
        x = np.asarray([[float(row[name]) for name in FEATURES] for row in rows], dtype=float)
        y = np.asarray([int(row["label"]) for row in rows], dtype=float)
        if not np.isfinite(x).all() or not np.isin(y, [0.0, 1.0]).all():
            raise ValueError("features must be finite and labels must be 0/1")
        return x, y

    x_train, y_train = matrix(train_rows)
    x_test, y_test = matrix(holdout_rows)
    if len(np.unique(y_train)) < 2:
        return {
            "status": "INSUFFICIENT_CLASS_VARIATION",
            "train_n": len(train_rows),
            "holdout_n": len(holdout_rows),
        }
    mean = x_train.mean(axis=0)
    scale = x_train.std(axis=0)
    scale[scale < 1e-12] = 1.0
    x_train = np.column_stack([np.ones(len(x_train)), (x_train - mean) / scale])
    x_test = np.column_stack([np.ones(len(x_test)), (x_test - mean) / scale])
    beta = np.zeros(x_train.shape[1], dtype=float)
    penalty = np.eye(len(beta)) * l2
    penalty[0, 0] = 0.0  # do not penalize intercept

    for _ in range(max_iter):
        eta = np.clip(x_train @ beta, -35.0, 35.0)
        prob = 1.0 / (1.0 + np.exp(-eta))
        weights = np.maximum(prob * (1.0 - prob), 1e-8)
        gradient = x_train.T @ (prob - y_train) + penalty @ beta
        hessian = (x_train.T * weights) @ x_train + penalty + np.eye(len(beta)) * 1e-10
        step = np.linalg.solve(hessian, gradient)
        beta -= step
        if float(np.max(np.abs(step))) < tolerance:
            break

    def predict(x):
        return 1.0 / (1.0 + np.exp(-np.clip(x @ beta, -35.0, 35.0)))

    def metrics(prob, y):
        clipped = np.clip(prob, 1e-12, 1.0 - 1e-12)
        bins = []
        ece = 0.0
        for low in np.linspace(0.0, 0.9, 10):
            high = low + 0.1
            mask = (prob >= low) & ((prob < high) if high < 1.0 else (prob <= high))
            count = int(mask.sum())
            if not count:
                continue
            predicted = float(np.mean(prob[mask]))
            observed = float(np.mean(y[mask]))
            ece += (count / len(y)) * abs(predicted - observed)
            bins.append(
                {
                    "lower_bound": float(low),
                    "upper_bound": float(high),
                    "n": count,
                    "mean_predicted_probability": predicted,
                    "observed_continuation_rate": observed,
                    "calibration_gap": observed - predicted,
                }
            )
        return {
            "log_loss": float(-np.mean(y * np.log(clipped) + (1.0 - y) * np.log(1.0 - clipped))),
            "brier_score": float(np.mean((prob - y) ** 2)),
            "observed_continuation_rate": float(np.mean(y)),
            "mean_predicted_probability": float(np.mean(prob)),
            "expected_calibration_error_10_bins": float(ece),
            "reliability_bins": bins,
        }

    holdout_prob = predict(x_test)
    baseline = float(np.mean(y_train))
    baseline_prob = np.full(len(y_test), baseline)
    return {
        "status": "FITTED_TRAIN_EVALUATED_HOLDOUT",
        "model": "L2-regularized logistic regression; Newton/IRLS; train-standardized features",
        "features": list(FEATURES),
        "l2": l2,
        "max_iter": max_iter,
        "train_n": len(train_rows),
        "holdout_n": len(holdout_rows),
        "train_metrics": metrics(predict(x_train), y_train),
        "holdout_metrics": metrics(holdout_prob, y_test),
        "holdout_train_prevalence_baseline_metrics": metrics(baseline_prob, y_test),
        "standardized_coefficients": {
            "intercept": float(beta[0]),
            **{name: float(beta[i + 1]) for i, name in enumerate(FEATURES)},
        },
        "interpretation_warning": "Predictive validity is not established by fitting. Compare holdout scores with the prevalence baseline; account for overlapping labels and serial dependence, calibrate probabilities, and test economic PnL net of costs before claiming an edge.",
    }


__all__ = ["FEATURES", "fit_evaluate_logistic"]
