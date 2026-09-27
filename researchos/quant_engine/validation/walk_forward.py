"""
Walk-Forward Validation — the validator engine.

Evaluates a ``ResearchDataset`` with realistic chronological walk-forward
validation, computing per-fold and aggregate metrics, and generating
deterministic research reports.

The validation layer only depends on the dataset contract; it never imports
(and therefore can never modify) ``FeatureBuilder``, ``LabelBuilder``, or
``DatasetBuilder``.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..machine_learning.dataset_contracts import ResearchDataset
from .contracts import (
    VALIDATION_VERSION,
    FoldResult,
    ValidationError,
    ValidationResult,
)
from .metrics import compute_metrics
from .splitter import Fold, WalkForwardSplitter


def _pairwise(seq: Sequence) -> list[tuple[object, object]]:
    values = list(seq)
    out: list[tuple[object, object]] = []
    for i in range(1, len(values)):
        out.append((values[i - 1], values[i]))
    return out


def _aggregate(fold_results: tuple[FoldResult, ...]) -> dict:
    """Mean of each metric across folds (deterministic)."""
    if not fold_results:
        return {}
    metric_names = sorted(fold_results[0].metrics.keys())
    agg: dict = {}
    for name in metric_names:
        values = [float(fr.metrics[name]) for fr in fold_results]
        agg[name] = sum(values) / len(values)
    return agg


class WalkForwardValidator:
    """Deterministic walk-forward validator for ``ResearchDataset``."""

    def __init__(
        self,
        train_size: int | None = None,
        validation_size: int | None = None,
        step_size: int | None = None,
        test_size: int | None = None,
    ) -> None:
        if train_size is None:
            raise ValidationError("train_size is required")
        if validation_size is None:
            raise ValidationError("validation_size is required")
        if step_size is None:
            raise ValidationError("step_size is required")

        if not isinstance(train_size, int) or train_size <= 0:
            raise ValidationError("train_size must be a positive integer")
        if not isinstance(validation_size, int) or validation_size <= 0:
            raise ValidationError("validation_size must be a positive integer")
        if not isinstance(step_size, int) or step_size <= 0:
            raise ValidationError("step_size must be a positive integer")
        if test_size is not None and (not isinstance(test_size, int) or test_size <= 0):
            raise ValidationError("test_size must be a positive integer when provided")

        self.train_size = train_size
        self.validation_size = validation_size
        self.step_size = step_size
        self.test_size = test_size
        self.splitter = WalkForwardSplitter(train_size, validation_size, step_size)

    # -- leakage protection -------------------------------------------------

    def _check_dataset(self, dataset: ResearchDataset) -> None:
        if not isinstance(dataset, ResearchDataset):
            raise TypeError("expected a ResearchDataset")
        required = self.train_size + self.validation_size
        if self.test_size is not None:
            required += self.test_size
        if dataset.sample_count < required:
            raise ValidationError(
                "dataset too small for the requested train/validation/holdout windows"
            )

    def _check_fold_leakage(self, folds: list[Fold], length: int) -> None:
        if not folds:
            raise ValidationError("empty folds detected")
        prev_val_start = -1
        # The first validation window starts after the initial training
        # window (train_size > 0), not at index 0.
        prev_val_end = folds[0].validation_start - 1
        for fold in folds:
            # Empty fold detection.
            if fold.train_size <= 0 or fold.validation_size <= 0:
                raise ValidationError("empty fold detected")
            # Chronological ordering: every new window must move forward.
            if fold.validation_start <= prev_val_start:
                raise ValidationError("folds are not strictly chronological")
            if fold.validation_start != prev_val_end + 1:
                # Folds may be separated by a gap only if that gap is the
                # reserved pseudo-test region.  Otherwise this is a leak.
                raise ValidationError("overlapping or gapped forbidden window detected")
            # Training data must not appear after validation data.
            if fold.train_end > fold.validation_start:
                raise ValidationError("training data appears after validation")
            # Future timestamp detection: no index may lie beyond the dataset.
            if fold.validation_end >= length:
                raise ValidationError("fold references future timestamps")
            prev_val_start = fold.validation_start
            prev_val_end = fold.validation_end
        # Reserve an untouched holdout tail after the last validation window.
        if self.test_size is None:
            if folds[-1].validation_end >= length - 1:
                raise ValidationError("no test data remains after final fold")
            return

        holdout_start = length - self.test_size
        if folds[-1].validation_end >= holdout_start:
            raise ValidationError("final validation window overlaps the holdout")
        if folds[-1].validation_end != holdout_start - 1:
            raise ValidationError(
                "final validation window must end immediately before the explicit holdout"
            )

    # -- core validation ----------------------------------------------------

    def _fold_predictions(self, dataset: ResearchDataset, fold: Fold) -> tuple[list[float], list[float]]:
        """Deterministic baseline predictor: predict the last training label
        for every validation sample.  This is a pure, leak-free baseline used
        to demonstrate the engine; callers can plug in their own predictors.
        """
        train_labels = [float(v) for v in dataset.labels[fold.train_start : fold.train_end + 1]]
        if not train_labels:
            raise ValidationError("empty training window")
        base = train_labels[-1]
        y_true = [float(v) for v in dataset.labels[fold.validation_start : fold.validation_end + 1]]
        y_pred = [base] * len(y_true)
        return y_true, y_pred

    def validate(self, dataset: ResearchDataset) -> ValidationResult:
        """Run full walk-forward validation and return aggregate results."""
        self._check_dataset(dataset)
        folds = self.splitter.split(dataset.sample_count)
        if self.test_size is not None:
            holdout_start = dataset.sample_count - self.test_size
            folds = [fold for fold in folds if fold.validation_end < holdout_start]
        self._check_fold_leakage(folds, dataset.sample_count)

        fold_results: list[FoldResult] = []
        for fold in folds:
            y_true, y_pred = self._fold_predictions(dataset, fold)
            fold_results.append(
                FoldResult(
                    fold_id=fold.fold_id,
                    train_range=fold.train_range,
                    validation_range=fold.validation_range,
                    metrics=compute_metrics(y_true, y_pred),
                    sample_count=len(y_true),
                )
            )

        test_size = self.test_size
        holdout_start = (
            dataset.sample_count - test_size
            if test_size is not None
            else folds[-1].validation_end + 1
        )
        if test_size is None:
            test_size = dataset.sample_count - holdout_start

        return ValidationResult(
            train_size=self.train_size,
            validation_size=self.validation_size,
            test_size=test_size,
            fold_count=len(fold_results),
            fold_results=tuple(fold_results),
            metrics=_aggregate(tuple(fold_results)),
            metadata={
                "validation_version": VALIDATION_VERSION,
                "step_size": self.step_size,
                "label_name": dataset.label_name,
                "dataset_version": dataset.version,
                "sample_count": dataset.sample_count,
                "holdout_range": [holdout_start, dataset.sample_count - 1],
                "holdout_is_untouched": True,
            },
        )

    def validate_folds(self, dataset: ResearchDataset) -> tuple[FoldResult, ...]:
        """Return the per-fold results without aggregation."""
        result = self.validate(dataset)
        return result.fold_results

    def generate_report(self, dataset: ResearchDataset) -> dict:
        """Return a deterministic, serializable report dict."""
        result = self.validate(dataset)
        report = result.to_dict()
        report["metadata"]["label_name"] = dataset.label_name
        report["metadata"]["feature_count"] = dataset.feature_count
        report["metadata"]["feature_names"] = list(dataset.feature_names)
        report["metadata"]["validation_version"] = VALIDATION_VERSION
        return report


__all__ = [
    "WalkForwardSplitter",
    "WalkForwardValidator",
    "Fold",
    "FoldResult",
    "ValidationResult",
    "ValidationError",
]
