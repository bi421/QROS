"""Deterministic, selection-aware multiple-testing controls.

These functions adjust p-values only; they do not create evidence or change
research hypotheses. The caller must retain the original hypothesis order and
selection count in the governed result manifest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class MultipleTestingReport:
    method: str
    family_size: int
    alpha: float
    adjusted_p_values: tuple[float, ...]
    reject: tuple[bool, ...]


def _validate(p_values: Sequence[float], alpha: float) -> None:
    if not p_values:
        raise ValueError("p_values must not be empty")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    if any(not 0.0 <= p <= 1.0 for p in p_values):
        raise ValueError("p_values must be in [0, 1]")


def bonferroni(p_values: Sequence[float], *, alpha: float = 0.05) -> MultipleTestingReport:
    """Bonferroni family-wise error-rate control."""
    _validate(p_values, alpha)
    m = len(p_values)
    adjusted = tuple(min(1.0, p * m) for p in p_values)
    return MultipleTestingReport("bonferroni", m, alpha, adjusted, tuple(p <= alpha for p in adjusted))


def benjamini_hochberg(p_values: Sequence[float], *, alpha: float = 0.05) -> MultipleTestingReport:
    """Benjamini-Hochberg false-discovery-rate control."""
    _validate(p_values, alpha)
    m = len(p_values)
    indexed = sorted(enumerate(p_values), key=lambda item: (item[1], item[0]))
    adjusted_sorted = [1.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        _, p = indexed[rank - 1]
        running = min(running, p * m / rank)
        adjusted_sorted[rank - 1] = min(1.0, running)
    adjusted = [0.0] * m
    for position, (original_index, _) in enumerate(indexed):
        adjusted[original_index] = adjusted_sorted[position]
    return MultipleTestingReport("benjamini_hochberg", m, alpha, tuple(adjusted), tuple(p <= alpha for p in adjusted))


__all__ = ["MultipleTestingReport", "benjamini_hochberg", "bonferroni"]
