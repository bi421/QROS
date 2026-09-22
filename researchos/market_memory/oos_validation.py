"""Leakage-safe walk-forward validation for Market Memory findings."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Protocol, Sequence, TypeVar

from researchos.market_memory.statistical_evidence import wilson_proportion_ci


class _TimestampedEvent(Protocol):
    timestamp: datetime


EventT = TypeVar("EventT", bound=_TimestampedEvent)


@dataclass(frozen=True)
class OOSFoldResult:
    """One chronological train/validation/test fold."""

    fold: int
    train_events: int
    validation_events: int
    test_events: int
    train_probability: float
    validation_probability: float
    test_probability: float
    train_mean: float
    validation_mean: float
    test_mean: float
    test_probability_ci: tuple[float, float] | None
    passed: bool
    notes: str = ""


@dataclass(frozen=True)
class OOSValidationResult:
    """Aggregate walk-forward validation result."""

    folds: tuple[OOSFoldResult, ...]
    passed_folds: int
    total_folds: int
    stable: bool
    status: str
    minimum_test_events: int
    validation_method: str = "walk_forward_expanding_purged"
    purge_days: int = 0
    embargo_days: int = 0
    fit_mode: str = "fixed_matcher"


def assert_label_boundaries(
    train_events: Sequence[EventT],
    validation_events: Sequence[EventT],
    test_events: Sequence[EventT],
    label_end_getter: Callable[[EventT], datetime | None],
) -> None:
    """Fail closed unless realized label windows stay inside their partition."""
    if not train_events or not validation_events or not test_events:
        return

    validation_start = min(event.timestamp for event in validation_events)
    test_start = min(event.timestamp for event in test_events)
    train_ends = [label_end_getter(event) for event in train_events]
    validation_ends = [label_end_getter(event) for event in validation_events]

    if any(value is None for value in train_ends):
        raise ValueError("label boundary audit requires realized end timestamp for every train event")
    if any(value is None for value in validation_ends):
        raise ValueError("label boundary audit requires realized end timestamp for every validation event")

    if max(train_ends) >= validation_start:
        raise ValueError("label boundary leakage: train label extends into validation")
    if max(validation_ends) >= test_start:
        raise ValueError("label boundary leakage: validation label extends into test")


def walk_forward_validate(
    events: Sequence[EventT],
    matcher: Callable[[EventT], bool],
    outcome_getter: Callable[[EventT], float | None],
    *,
    initial_train_size: int = 100,
    validation_size: int = 50,
    test_size: int = 50,
    step_size: int = 50,
    min_test_events: int = 20,
    confidence_level: float = 0.95,
    purge_days: int = 0,
    embargo_days: int = 0,
    max_outcome_horizon_days: int | None = None,
    label_end_getter: Callable[[EventT], datetime | None] | None = None,
    fit_callback: Callable[[Sequence[EventT]], Callable[[EventT], bool]] | None = None,
) -> OOSValidationResult:
    """Evaluate a condition with chronological, purged walk-forward folds.

    ``fit_callback`` is an optional train-only fitting hook. When supplied,
    each fold calls it with the purged training events and expects a matcher
    built from that training data. The fitted matcher is then applied to the
    train, validation, and test partitions. The callback is never given
    validation or test events, making the train-only fitting boundary explicit.

    With ``fit_callback=None`` the legacy fixed ``matcher`` behavior is
    preserved exactly.
    """
    if initial_train_size < 1 or validation_size < 1 or test_size < 1:
        raise ValueError("window sizes must be >= 1")
    if step_size < 1 or min_test_events < 1:
        raise ValueError("step_size and min_test_events must be >= 1")
    if purge_days < 0 or embargo_days < 0:
        raise ValueError("purge_days and embargo_days must be >= 0")
    if max_outcome_horizon_days is not None and max_outcome_horizon_days < 1:
        raise ValueError("max_outcome_horizon_days must be >= 1 when supplied")
    if max_outcome_horizon_days is not None and purge_days < max_outcome_horizon_days:
        raise ValueError("purge_days must be >= max_outcome_horizon_days to prevent label leakage")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be strictly between 0 and 1")

    ordered = list(events)
    for i in range(1, len(ordered)):
        if ordered[i].timestamp <= ordered[i - 1].timestamp:
            raise ValueError("events must have strictly increasing timestamps")

    results: list[OOSFoldResult] = []
    train_end = initial_train_size
    fold = 0
    while train_end + validation_size + test_size <= len(ordered):
        validation_start = ordered[train_end].timestamp
        validation_end_index = train_end + validation_size
        test_start_index = validation_end_index
        test_start = ordered[test_start_index].timestamp
        test_end_index = test_start_index + test_size
        test_end = ordered[test_end_index - 1].timestamp

        purge_delta = timedelta(days=purge_days)
        embargo_delta = timedelta(days=embargo_days)
        train_cutoff = validation_start - purge_delta
        validation_cutoff = test_start - purge_delta
        train = [event for event in ordered[:train_end] if event.timestamp < train_cutoff]
        validation = [
            event for event in ordered[train_end:validation_end_index]
            if event.timestamp >= validation_start and event.timestamp < validation_cutoff
        ]
        test_lower_bound = test_start + embargo_delta
        test = [
            event for event in ordered[test_start_index:test_end_index]
            if event.timestamp >= test_lower_bound and event.timestamp <= test_end
        ]

        if label_end_getter is not None:
            assert_label_boundaries(train, validation, test, label_end_getter)

        fold_matcher = matcher
        if fit_callback is not None:
            fold_matcher = fit_callback(tuple(train))
            if not callable(fold_matcher):
                raise TypeError("fit_callback must return a callable matcher")

        train_values = _matched_values(train, fold_matcher, outcome_getter)
        validation_values = _matched_values(validation, fold_matcher, outcome_getter)
        test_values = _matched_values(test, fold_matcher, outcome_getter)
        test_successes = sum(v > 0.0 for v in test_values)
        ci = (
            wilson_proportion_ci(test_successes, len(test_values), confidence_level).confidence_interval
            if test_values else None
        )
        train_prob = _probability(train_values)
        validation_prob = _probability(validation_values)
        test_prob = _probability(test_values)
        passed = len(test_values) >= min_test_events and _stable(train_prob, validation_prob, test_prob)
        note = "" if passed else "Insufficient OOS sample or unstable probability"
        results.append(
            OOSFoldResult(
                fold=fold,
                train_events=len(train_values),
                validation_events=len(validation_values),
                test_events=len(test_values),
                train_probability=train_prob,
                validation_probability=validation_prob,
                test_probability=test_prob,
                train_mean=_mean(train_values),
                validation_mean=_mean(validation_values),
                test_mean=_mean(test_values),
                test_probability_ci=ci,
                passed=passed,
                notes=note,
            )
        )
        fold += 1
        train_end += step_size

    passed = sum(r.passed for r in results)
    stable = bool(results) and passed == len(results)
    status = "VALIDATED" if stable else ("INCONCLUSIVE" if results else "INSUFFICIENT_DATA")
    return OOSValidationResult(
        tuple(results), passed, len(results), stable, status, min_test_events,
        purge_days=purge_days, embargo_days=embargo_days,
        fit_mode="train_only_fit" if fit_callback is not None else "fixed_matcher",
    )


def _matched_values(events: Sequence[EventT], matcher: Callable[[EventT], bool], getter: Callable[[EventT], float | None]) -> list[float]:
    values: list[float] = []
    for event in events:
        if matcher(event):
            value = getter(event)
            if value is not None and math.isfinite(float(value)):
                values.append(float(value))
    return values


def _probability(values: Sequence[float]) -> float:
    return sum(v > 0.0 for v in values) / len(values) if values else 0.0


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stable(train: float, validation: float, test: float, tolerance: float = 0.15) -> bool:
    return max(train, validation, test) - min(train, validation, test) <= tolerance


__all__ = ["OOSFoldResult", "OOSValidationResult", "assert_label_boundaries", "walk_forward_validate"]
