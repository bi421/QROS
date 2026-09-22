"""
Explainability and Uncertainty Quantification for Deep Learning Models.

Implements:
    - SHAP-like feature importance (permutation-based, no external SHAP dependency)
    - Monte Carlo dropout uncertainty quantification
    - Feature attribution via integrated gradients approximation
    - Confidence intervals for predictions
"""

from __future__ import annotations

from typing import Protocol, cast

import numpy as np


class _ExplainabilityModel(Protocol):
    def forward(
        self,
        X: np.ndarray,
        training: bool = False,
        mc_dropout: bool = False,
    ) -> np.ndarray: ...


def permutation_importance(
    model: _ExplainabilityModel,
    X: np.ndarray,
    y: np.ndarray,
    n_repeats: int = 10,
    rng: np.random.Generator | None = None,
) -> dict[str, np.ndarray | float]:
    """Compute permutation-based feature importance.

    Args:
        model: Model with forward(X) -> predictions method.
        X: Input features (batch, seq_len, features).
        y: True targets.
        n_repeats: Number of permutation repetitions per feature.
        rng: Random number generator.

    Returns:
        Dict with feature names, importance scores, and std.
    """
    if rng is None:
        rng = np.random.default_rng(42)

    n_features = X.shape[-1]
    baseline_pred = model.forward(X, training=False)
    baseline_loss = _mse(baseline_pred, y)

    importance = np.zeros(n_features, dtype=np.float32)
    importance_std = np.zeros(n_features, dtype=np.float32)

    for feat_idx in range(n_features):
        losses: list[float] = []
        for _ in range(n_repeats):
            X_permuted = X.copy()
            perm_idx = rng.permutation(X.shape[0])
            X_permuted[:, :, feat_idx] = X_permuted[perm_idx, :, feat_idx]
            perm_pred = model.forward(X_permuted, training=False)
            perm_loss = _mse(perm_pred, y)
            losses.append(perm_loss - baseline_loss)
        importance[feat_idx] = np.mean(losses)
        importance_std[feat_idx] = np.std(losses)

    return {
        "importance": importance,
        "importance_std": importance_std,
        "baseline_loss": baseline_loss,
    }


def integrated_gradients(
    model: _ExplainabilityModel,
    X: np.ndarray,
    baseline: np.ndarray | None = None,
    n_steps: int = 50,
) -> np.ndarray:
    """Approximate integrated gradients for feature attribution.

    Args:
        model: Model with forward(X) -> predictions method.
        X: Input instance (batch=1, seq_len, features) or (seq_len, features).
        baseline: Baseline input (defaults to zeros).
        n_steps: Number of interpolation steps.

    Returns:
        Attribution scores (seq_len, features).
    """
    if baseline is None:
        baseline = np.zeros_like(X)

    alphas = np.linspace(0, 1, n_steps)
    attributions = np.zeros_like(X)

    for alpha in alphas:
        X_interp = baseline + alpha * (X - baseline)
        X_interp_tensor = X_interp[np.newaxis, ...] if X_interp.ndim == 2 else X_interp
        pred = model.forward(X_interp_tensor, training=False)
        # Gradient approximation via finite differences
        eps = 1e-4
        grad = np.zeros_like(X_interp)
        for feat_idx in range(X_interp.shape[-1]):
            X_plus = X_interp.copy()
            X_plus[..., feat_idx] += eps
            X_plus_tensor = X_plus[np.newaxis, ...] if X_plus.ndim == 2 else X_plus
            pred_plus = model.forward(X_plus_tensor, training=False)
            grad[..., feat_idx] = (pred_plus - pred) / eps
        attributions += grad

    attributions = attributions * (X - baseline) / n_steps
    return cast(np.ndarray, attributions)


def monte_carlo_dropout(
    model: _ExplainabilityModel,
    X: np.ndarray,
    n_samples: int = 100,
    rng: np.random.Generator | None = None,
) -> dict[str, np.ndarray]:
    """Monte Carlo dropout for uncertainty quantification.

    Args:
        model: Model with forward(X, training=True, mc_dropout=True) method.
        X: Input features (batch, seq_len, features).
        n_samples: Number of MC samples.
        rng: Random number generator.

    Returns:
        Dict with mean predictions, std, and confidence intervals.
    """
    if rng is None:
        rng = np.random.default_rng(42)

    samples: list[np.ndarray] = []
    for _ in range(n_samples):
        pred = model.forward(X, training=False, mc_dropout=True)
        samples.append(pred)
    preds = np.stack(samples, axis=0)

    mean = np.mean(preds, axis=0)
    std = np.std(preds, axis=0)
    ci_lower = np.percentile(preds, 2.5, axis=0)
    ci_upper = np.percentile(preds, 97.5, axis=0)

    return {
        "mean": mean,
        "std": std,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "samples": preds,
    }


def prediction_confidence(
    model: _ExplainabilityModel,
    X: np.ndarray,
    n_samples: int = 100,
) -> np.ndarray:
    """Compute prediction confidence as inverse of normalized MC dropout std."""
    mc_results = monte_carlo_dropout(model, X, n_samples)
    std = mc_results["std"]
    max_std = np.max(std) if np.max(std) > 0 else 1.0
    confidence = 1.0 - (std / max_std)
    return np.clip(confidence, 0.0, 1.0)


def _mse(y_pred: np.ndarray, y_true: np.ndarray) -> float:
    return float(np.mean((y_pred - y_true) ** 2))


def compute_confidence_intervals(
    predictions: np.ndarray,
    confidence: float = 0.95,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute confidence intervals for predictions."""
    alpha = 1.0 - confidence
    lower = np.percentile(predictions, 100 * alpha / 2, axis=0)
    upper = np.percentile(predictions, 100 * (1 - alpha / 2), axis=0)
    return lower, upper


__all__ = [
    "permutation_importance",
    "integrated_gradients",
    "monte_carlo_dropout",
    "prediction_confidence",
    "compute_confidence_intervals",
]
