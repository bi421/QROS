"""Small deterministic probability primitives.

These functions intentionally avoid opaque model fitting. Advanced econometric,
tail and multiple-testing methods will consume the same explicit contracts.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence


def expected_value(probabilities: Sequence[float], outcomes: Sequence[float]) -> float:
    """Return E[X] for a finite discrete distribution."""
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValueError("probabilities and outcomes must have the same non-zero length")
    if any(p < 0 or not math.isfinite(p) for p in probabilities):
        raise ValueError("probabilities must be finite and non-negative")
    total = math.fsum(probabilities)
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("probabilities must sum to 1")
    return math.fsum(p * x for p, x in zip(probabilities, outcomes, strict=True))


def kelly_fraction(win_probability: float, loss_probability: float, win_loss_odds: float) -> float:
    """Return idealized binary Kelly fraction f* = (bp-q)/b.

    This is a mathematical sizing result, not a live-risk recommendation. Inputs
    must represent net win/loss odds and declared probabilities.
    """
    if not 0.0 <= win_probability <= 1.0:
        raise ValueError("win_probability must be in [0, 1]")
    if not 0.0 <= loss_probability <= 1.0:
        raise ValueError("loss_probability must be in [0, 1]")
    if not math.isclose(win_probability + loss_probability, 1.0, abs_tol=1e-12):
        raise ValueError("win_probability + loss_probability must equal 1")
    if not math.isfinite(win_loss_odds) or win_loss_odds <= 0:
        raise ValueError("win_loss_odds must be finite and > 0")
    return (win_loss_odds * win_probability - loss_probability) / win_loss_odds


def shannon_entropy(values: Iterable[object], *, base: float = 2.0) -> float:
    """Return Shannon entropy of a finite discrete sample."""
    if base <= 0 or math.isclose(base, 1.0):
        raise ValueError("base must be positive and different from 1")
    sample = list(values)
    if not sample:
        raise ValueError("values must not be empty")
    counts = Counter(sample)
    n = len(sample)
    return -math.fsum((count / n) * math.log(count / n, base) for count in counts.values())


def mutual_information(x: Iterable[object], y: Iterable[object], *, base: float = 2.0) -> float:
    """Return plug-in mutual information for paired discrete observations."""
    if base <= 0 or math.isclose(base, 1.0):
        raise ValueError("base must be positive and different from 1")
    x_values = list(x)
    y_values = list(y)
    if len(x_values) != len(y_values) or not x_values:
        raise ValueError("x and y must have the same non-zero length")
    n = len(x_values)
    joint = Counter(zip(x_values, y_values, strict=True))
    x_count = Counter(x_values)
    y_count = Counter(y_values)
    return math.fsum(
        (count / n)
        * math.log((count * n) / (x_count[xv] * y_count[yv]), base)
        for (xv, yv), count in joint.items()
    )


def _validate_returns(returns: Sequence[float]) -> list[float]:
    values = [float(value) for value in returns]
    if not values:
        raise ValueError("returns must not be empty")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("returns must contain only finite values")
    return values


def historical_var(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Return historical loss VaR at the requested confidence level.

    Returns are converted to losses as -return; linear interpolation is used
    between ordered observations. The sign convention is positive loss.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    losses = sorted(-value for value in _validate_returns(returns))
    position = (len(losses) - 1) * confidence
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return losses[lower]
    weight = position - lower
    return losses[lower] + weight * (losses[upper] - losses[lower])


def historical_expected_shortfall(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Return empirical expected shortfall as mean loss in the tail beyond VaR."""
    var = historical_var(returns, confidence)
    losses = sorted(-value for value in _validate_returns(returns))
    tail = [loss for loss in losses if loss >= var]
    if not tail:
        raise ValueError("tail is empty")
    return math.fsum(tail) / len(tail)
