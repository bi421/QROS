"""
ML vs Indicators comparison - purged k-fold and indicator metrics functions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from researchos.engines.quant.machine_learning.deep_models import MLPRegressor
from researchos.engines.quant.machine_learning.features import (
    compute_indicator_metrics,
    generate_features,
    generate_signals_vectorized,
)
from researchos.engines.quant.machine_learning.purged_validation import (
    purged_k_fold as _purged_k_fold_impl,
)


@dataclass
class MLComparisonResult:
    """Results from ML vs indicators comparison."""

    ml_metrics: dict
    indicator_metrics: dict
    comparison: dict
    fold_results: List[dict]
    feature_importance: Optional[dict] = None
    timing: dict = field(default_factory=dict)


def run_ml_comparison(
    close: np.ndarray,
    volumes: np.ndarray,
    lookback: int = 60,
    n_splits: int = 5,
    purge_gap: int = 5,
    embargo_gap: int = 5,
    train_ratio: float = 0.7,
    epochs: int = 50,
    batch_size: int = 32,
    confidence_threshold: float = 0.6,
    commission: float = 0.0001,
    random_state: int = 42,
) -> MLComparisonResult:
    """Run ML vs indicators comparison with purged k-fold validation."""

    start_time = time.time()

    # Build features
    features = generate_features(
        close=close,
        volumes=volumes,
        lookback=lookback,
    )

    # Build labels
    labels = compute_label_returns(close, forward_periods=5)

    # Mask valid rows
    valid_mask = ~(np.isnan(features).any(axis=1) | np.isnan(labels))
    X = features[valid_mask]
    y = labels[valid_mask]

    if len(X) == 0:
        raise ValueError("No valid data points after masking")

    # Purged k-fold cross-validation
    n_samples = len(X)
    folds = _purged_k_fold_impl(n_samples, n_splits, purge_gap, embargo_gap)
    fold_results = []

    for i, fold in enumerate(folds):
        fold_start = time.time()

        # Split data
        X_train, X_test = X[fold.train_indices], X[fold.test_indices]
        y_train, y_test = y[fold.train_index], y[fold.test_index]

        # Train MLP
        model = MLPRegressor(
            input_dim=X_train.shape[1],
            hidden_dim=64,
            output_dim=1,
            dropout_rate=0.2,
            random_state=random_state,
        )

        model.train(X_train, y_train, epochs=epochs, batch_size=batch_size)

        # Predict on test
        y_pred = model.forward(X_test, training=False)

        # Compute metrics
        test_mse = np.mean((y_pred.flatten() - y_test) ** 2)
        test_mae = np.mean(np.abs(y_pred.flatten() - y_test))

        # Direction accuracy
        pred_direction = (y_pred.flatten() > 0).astype(int)
        true_direction = (y_test > 0).astype(int)
        direction_accuracy = np.mean(pred_direction == true_direction)

        # SHAP-like feature importance (correlation-based)
        if i == 0:  # Only compute for first fold
            correlations = np.abs(np.corrcoef(X_train.T, y_train)[:-1, -1])
            feature_importance = {
                "method": "correlation",
                "importances": correlations.tolist(),
                "top_features": np.argsort(correlations)[::-1].tolist()[:10],
            }

        fold_result = {
            "fold": i + 1,
            "train_size": len(X_train),
            "test_size": len(X_test),
            "test_mse": float(test_mse),
            "test_mae": float(test_mae),
            "direction_accuracy": float(direction_accuracy),
            "timing": {"fit": time.time() - fold_start},
        }
        fold_results.append(fold_result)

        print(f"Fold {i + 1}/{n_splits}: MSE={test_mse:.6f}, DA={direction_accuracy:.3f}")

    # Aggregate ML metrics
    ml_metrics = {
        "mean_test_mse": np.mean([fr["test_mse"] for fr in fold_results]),
        "std_test_mse": np.std([fr["test_mse"] for fr in fold_results]),
        "mean_direction_accuracy": np.mean([fr["direction_accuracy"] for fr in fold_results]),
        "n_folds": n_splits,
        "total_time": time.time() - start_time,
    }

    # Run indicator strategy
    indicator_metrics = run_indicator_strategy(
        close=close,
        commission=commission,
        confidence_threshold=confidence_threshold,
    )

    # Compare
    comparison = {
        "ml_direction_accuracy": ml_metrics["mean_direction_accuracy"],
        "indicator_win_rate": indicator_metrics.get("win_rate", 0),
        "ml_vs_indicator_delta": ml_metrics["mean_direction_accuracy"] - indicator_metrics.get("win_rate", 0),
    }

    timing = {
        "total_time": time.time() - start_time,
        "ml_time": ml_metrics["total_time"],
        "indicator_time": indicator_metrics.get("total_time", 0),
    }

    result = MLComparisonResult(
        ml_metrics=ml_metrics,
        indicator_metrics=indicator_metrics,
        comparison=comparison,
        fold_results=fold_results,
        feature_importance=feature_importance,
        timing=timing,
    )

    print("\n=== ML vs Indicators Summary ===")
    print(f"ML Direction Accuracy: {comparison['ml_direction_accuracy']:.3f}")
    print(f"Indicator Win Rate:    {comparison['indicator_win_rate']:.3f}")
    print(f"Delta:                 {comparison['ml_vs_indicator_delta']:+.3f}")

    return result


def run_indicator_strategy(
    close: np.ndarray,
    lookback: int = 60,
    commission: float = 0.0001,
    confidence_threshold: float = 0.6,
) -> dict:
    """Run indicator-based trading strategy."""
    start_time = time.time()

    # Generate signals from indicators
    signals = generate_signals_vectorized(close, lookback=lookback)

    # Simulate trades
    trades = simulate_trades_vectorized(
        close=close,
        signals=signals,
        commission=commission,
    )

    # Compute metrics
    metrics = compute_indicator_metrics(trades)
    metrics["total_time"] = time.time() - start_time

    return metrics


def simulate_trades_vectorized(
    close: np.ndarray,
    signals: np.ndarray,
    commission: float = 0.0001,
) -> List[dict]:
    """Simulate trades from signals vectorized."""
    trades = []
    position = 0
    entry_price = 0.0

    for i in range(1, len(close)):
        signal = signals[i]

        if signal > 0 and position == 0:  # Buy signal
            position = 1
            entry_price = close[i]
        elif signal < 0 and position == 1:  # Sell signal
            position = 0
            exit_price = close[i]
            pnl = (exit_price - entry_price) / entry_price - commission
            trades.append(
                {
                    "entry_idx": int(np.where(signals[:i] == 1)[0][-1]) if len(np.where(signals[:i] == 1)[0]) > 0 else 0,
                    "exit_idx": i,
                    "entry_price": float(entry_price),
                    "exit_price": float(exit_price),
                    "pnl_pct": float(pnl * 100),
                    "duration": i - int(np.where(signals[:i] == 1)[0][-1]) if len(np.where(signals[:i] == 1)[0]) > 0 else 0,
                }
            )

    return trades


def compute_label_returns(
    close: np.ndarray,
    forward_periods: int = 5,
) -> np.ndarray:
    """Compute forward returns as labels."""
    returns = np.diff(np.log(close))
    forward_returns = np.zeros(len(returns))

    for i in range(len(returns) - forward_periods):
        forward_returns[i] = np.mean(returns[i : i + forward_periods])

    return forward_returns[:-forward_periods]
