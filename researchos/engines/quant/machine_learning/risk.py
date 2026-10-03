"""
Risk Management for ML-based Trading.

Implements:
    - Confidence-based position sizing
    - Kelly criterion with model confidence
    - Uncertainty-adjusted position sizing (Monte Carlo dropout)
    - Maximum drawdown control
    - Volatility targeting
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class PositionSizingResult:
    """Result of position sizing calculation."""

    position_size: float
    confidence: float
    uncertainty: float
    kelly_fraction: float
    max_position: float
    vol_target: float
    metadata: dict[str, Any] | None = None


def confidence_based_sizing(
    prediction: float,
    confidence: float,
    uncertainty: float,
    base_size: float = 1.0,
    max_size: float = 2.0,
    uncertainty_penalty: float = 0.5,
) -> float:
    """Size position based on model confidence and uncertainty.

    Args:
        prediction: Model prediction (e.g., expected return).
        confidence: Model confidence [0, 1].
        uncertainty: Model uncertainty (std from MC dropout).
        base_size: Base position size.
        max_size: Maximum position size.
        uncertainty_penalty: Penalty factor for high uncertainty.

    Returns:
        Position size multiplier.
    """
    if uncertainty <= 0:
        uncertainty_penalty = 0.0

    # Reduce size when uncertainty is high
    uncertainty_adj = max(0.0, 1.0 - uncertainty_penalty * uncertainty)
    size = base_size * confidence * uncertainty_adj

    # Direction from prediction
    direction = 1.0 if prediction > 0 else -1.0

    return direction * min(abs(size), max_size)


def kelly_criterion_with_confidence(
    win_prob: float,
    avg_win: float,
    avg_loss: float,
    confidence: float,
    max_fraction: float = 0.25,
) -> float:
    """Kelly criterion adjusted by model confidence.

    Args:
        win_prob: Probability of winning [0, 1].
        avg_win: Average win size (positive).
        avg_loss: Average loss size (positive).
        confidence: Model confidence [0, 1].
        max_fraction: Maximum fraction of capital to risk.

    Returns:
        Kelly fraction adjusted by confidence.
    """
    if avg_loss <= 0 or win_prob <= 0 or win_prob >= 1:
        return 0.0

    b = avg_win / avg_loss
    q = 1.0 - win_prob
    kelly = (b * win_prob - q) / b
    kelly = max(0.0, kelly)

    # Adjust by confidence
    adjusted_kelly = kelly * confidence

    return min(adjusted_kelly, max_fraction)


def volatility_targeting(
    prediction: float,
    current_volatility: float,
    target_volatility: float = 0.15,
    max_leverage: float = 3.0,
) -> float:
    """Scale position to target volatility.

    Args:
        prediction: Model prediction (expected return).
        current_volatility: Current realized volatility (annualized).
        target_volatility: Target annualized volatility.
        max_leverage: Maximum leverage allowed.

    Returns:
        Position size multiplier.
    """
    if current_volatility <= 1e-9:
        return 0.0

    vol_scalar = target_volatility / current_volatility
    leverage = min(vol_scalar, max_leverage)

    direction = 1.0 if prediction > 0 else -1.0
    return direction * leverage * np.sign(prediction) if prediction != 0 else 0.0


def max_drawdown_control(
    equity_curve: np.ndarray,
    max_drawdown_limit: float = 0.10,
    current_position: float = 1.0,
) -> float:
    """Reduce position size if approaching max drawdown limit.

    Args:
        equity_curve: Historical equity curve.
        max_drawdown_limit: Maximum allowed drawdown (e.g., 0.10 = 10%).
        current_position: Current position size.

    Returns:
        Adjusted position size.
    """
    if len(equity_curve) < 2:
        return current_position

    peak = np.maximum.accumulate(equity_curve)
    drawdown = (peak - equity_curve) / peak
    current_dd = float(np.max(drawdown))

    if current_dd >= max_drawdown_limit:
        return 0.0

    # Scale down linearly as we approach the limit
    if current_dd >= max_drawdown_limit * 0.8:
        scale = 1.0 - (current_dd - max_drawdown_limit * 0.8) / (max_drawdown_limit * 0.2)
        return current_position * max(0.0, scale)

    return current_position


def combined_position_sizing(
    prediction: float,
    confidence: float,
    uncertainty: float,
    win_prob: float,
    avg_win: float,
    avg_loss: float,
    current_volatility: float,
    equity_curve: np.ndarray | None = None,
    base_size: float = 1.0,
    max_size: float = 2.0,
) -> PositionSizingResult:
    """Combine multiple sizing methods into a single position size.

    Args:
        prediction: Model prediction (expected return).
        confidence: Model confidence [0, 1].
        uncertainty: Model uncertainty (std from MC dropout).
        win_prob: Probability of winning.
        avg_win: Average win size.
        avg_loss: Average loss size.
        current_volatility: Current realized volatility.
        equity_curve: Historical equity curve for drawdown control.
        base_size: Base position size.
        max_size: Maximum position size.

    Returns:
        PositionSizingResult with final position size.
    """
    # Method 1: Confidence-based
    conf_size = confidence_based_sizing(prediction, confidence, uncertainty, base_size, max_size)

    # Method 2: Kelly criterion
    kelly = kelly_criterion_with_confidence(win_prob, avg_win, avg_loss, confidence, max_fraction=max_size)

    # Method 3: Volatility targeting
    vol_size = volatility_targeting(prediction, current_volatility)

    # Combine: take minimum of confidence and Kelly, apply volatility scaling
    combined = min(abs(conf_size), kelly, abs(vol_size))
    direction = 1.0 if prediction > 0 else -1.0
    final_size = direction * combined

    # Apply drawdown control
    if equity_curve is not None and len(equity_curve) > 0:
        final_size = max_drawdown_control(equity_curve, current_position=final_size)

    return PositionSizingResult(
        position_size=float(final_size),
        confidence=float(confidence),
        uncertainty=float(uncertainty),
        kelly_fraction=float(kelly),
        max_position=float(max_size),
        vol_target=float(current_volatility),
        metadata={
            "confidence_size": float(conf_size),
            "kelly_size": float(kelly),
            "volatility_size": float(vol_size),
        },
    )


def uncertainty_adjusted_returns(
    predictions: np.ndarray,
    uncertainties: np.ndarray,
    returns: np.ndarray,
    confidence_threshold: float = 0.6,
) -> dict[str, Any]:
    """Filter trades by model confidence and compute adjusted metrics.

    Args:
        predictions: Model predictions.
        uncertainties: Model uncertainties.
        returns: Actual returns.
        confidence_threshold: Minimum confidence to include trade.

    Returns:
        Dict with filtered metrics.
    """
    if len(predictions) == 0:
        return {"filtered_trades": 0, "filtered_return": 0.0, "filtered_sharpe": 0.0}

    confidence = 1.0 / (1.0 + uncertainties)
    mask = confidence >= confidence_threshold

    predictions[mask]
    filtered_ret = returns[mask]

    if len(filtered_ret) == 0:
        return {"filtered_trades": 0, "filtered_return": 0.0, "filtered_sharpe": 0.0}

    sharpe = 0.0
    if len(filtered_ret) > 1 and filtered_ret.std() > 1e-9:
        sharpe = math.sqrt(252) * (filtered_ret.mean() / filtered_ret.std())

    return {
        "filtered_trades": int(len(filtered_ret)),
        "filtered_return": float(np.sum(filtered_ret)),
        "filtered_sharpe": float(sharpe),
        "mean_confidence": float(np.mean(confidence[mask])),
        "mean_uncertainty": float(np.mean(uncertainties[mask])),
    }


__all__ = [
    "PositionSizingResult",
    "confidence_based_sizing",
    "kelly_criterion_with_confidence",
    "volatility_targeting",
    "max_drawdown_control",
    "combined_position_sizing",
    "uncertainty_adjusted_returns",
]
