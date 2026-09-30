""""Deterministic multivariate empirical probability estimator for Phase 5.2.

This estimator is intentionally small: each selected feature is normalized using
training-window min/max bounds, validation rows are ranked by deterministic
squared Euclidean distance, and class frequencies among the fixed k nearest
training observations form the prediction probabilities. No randomness or
external ML library is used.
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np


class MultivariateEmpiricalProbabilityEstimator:
    """Leakage-safe deterministic k-nearest-neighbour empirical estimator."""

    def __init__(self, *, feature_indices: Sequence[int], n_neighbors: int = 25) -> None:
        self.feature_indices = tuple(int(i) for i in feature_indices)
        self.n_neighbors = int(n_neighbors)
        if not self.feature_indices:
            raise ValueError("At least one feature must be selected")
        if self.n_neighbors <= 0:
            raise ValueError("n_neighbors must be positive")
        self._mins: tuple[float, ...] = ()
        self._spans: tuple[float, ...] = ()
        self._train_rows = np.empty((0, len(self.feature_indices)), dtype=np.float64)
        self._labels: tuple[int, ...] = ()
        self._trained = False

    def fit(
        self,
        features: Sequence[Sequence[float | None]],
        labels: Sequence[float],
    ) -> "MultivariateEmpiricalProbabilityEstimator":
        if len(features) != len(labels):
            raise ValueError("features and labels must have equal length")
        if not features:
            raise ValueError("Training data must not be empty")
        selected_rows: list[tuple[float, ...]] = []
        selected_labels: list[int] = []
        for row, label in zip(features, labels):
            values = tuple(float(row[i]) for i in self.feature_indices)
            if any(v != v for v in values):
                raise ValueError("Selected training features must be finite")
            selected_rows.append(values)
            selected_labels.append(int(label))
        mins = tuple(
            min(row[j] for row in selected_rows)
            for j in range(len(self.feature_indices))
        )
        maxs = tuple(
            max(row[j] for row in selected_rows)
            for j in range(len(self.feature_indices))
        )
        spans = tuple(
            (maxs[j] - mins[j]) if maxs[j] != mins[j] else 1.0
            for j in range(len(mins))
        )
        self._mins = mins
        self._spans = spans
        self._train_rows = np.asarray(
            [self._normalize(row) for row in selected_rows],
            dtype=np.float64,
        )
        self._labels = tuple(selected_labels)
        self._trained = True
        return self

    def _normalize(self, row: Sequence[float]) -> tuple[float, ...]:
        return tuple(
            (float(row[j]) - self._mins[j]) / self._spans[j]
            for j in range(len(self.feature_indices))
        )

    def _nearest_indices(self, feature_row: Sequence[float | None]) -> list[int]:
        if not self._trained:
            raise ValueError("Estimator not fitted")
        values = tuple(float(feature_row[i]) for i in self.feature_indices)
        if any(v != v for v in values):
            raise ValueError("Selected prediction features must be finite")
        normalized = np.asarray(self._normalize(values), dtype=np.float64)
        k = min(self.n_neighbors, len(self._train_rows))

        # Preserve the historical ordering contract: distance first, then
        # original row index for deterministic ties. NumPy performs the
        # distance calculation in native code instead of a Python inner loop.
        deltas = self._train_rows - normalized
        distances = np.einsum("ij,ij->i", deltas, deltas)
        indices = np.arange(len(self._train_rows), dtype=np.int64)
        order = np.lexsort((indices, distances))
        return order[:k].tolist()

    def predict_proba(self, feature_row: Sequence[float | None]) -> dict[int, float]:
        indices = self._nearest_indices(feature_row)
        counts = {1: 0, 0: 0, -1: 0}
        for i in indices:
            cls = self._labels[i]
            if cls in counts:
                counts[cls] += 1
        total = sum(counts.values())
        if total == 0:
            return {1: 1 / 3, 0: 1 / 3, -1: 1 / 3}
        return {cls: counts[cls] / total for cls in (1, 0, -1)}

    def predict_class(self, feature_row: Sequence[float | None]) -> int:
        probs = self.predict_proba(feature_row)
        best = 1
        best_prob = -1.0
        for cls in (1, 0, -1):
            if probs[cls] > best_prob:
                best_prob = probs[cls]
                best = cls
        return best


__all__ = ["MultivariateEmpiricalProbabilityEstimator"]
