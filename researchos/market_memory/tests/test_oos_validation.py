"""Regression tests for walk-forward OOS validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from researchos.market_memory.oos_validation import walk_forward_validate


@dataclass(frozen=True)
class E:
    timestamp: datetime
    value: float
    match: bool = True


def _events(n: int = 300, value: float = 0.01) -> list[E]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [E(start + timedelta(days=i), value) for i in range(n)]


def test_walk_forward_is_chronological_and_validates_stable_condition():
    result = walk_forward_validate(
        _events(),
        lambda e: e.match,
        lambda e: e.value,
        initial_train_size=100,
        validation_size=50,
        test_size=50,
        step_size=50,
        min_test_events=20,
    )
    assert result.total_folds == 3
    assert result.status == "VALIDATED"
    assert result.stable is True
    assert all(f.test_events >= 20 for f in result.folds)
    assert result.fit_mode == "fixed_matcher"


def test_walk_forward_rejects_duplicate_or_reordered_timestamps():
    events = _events(120)
    events[5] = E(events[4].timestamp, 0.01)
    with pytest.raises(ValueError, match="strictly increasing"):
        walk_forward_validate(
            events,
            lambda e: True,
            lambda e: e.value,
            initial_train_size=40,
            validation_size=20,
            test_size=20,
        )


def test_walk_forward_is_inconclusive_with_small_oos_samples():
    result = walk_forward_validate(
        _events(),
        lambda e: e.match,
        lambda e: e.value,
        initial_train_size=100,
        validation_size=50,
        test_size=50,
        step_size=50,
        min_test_events=60,
    )
    assert result.status == "INCONCLUSIVE"
    assert result.stable is False


def test_train_only_fit_callback_never_receives_validation_or_test_events():
    events = _events(260)
    seen: list[tuple[datetime, ...]] = []

    def fit(train_events):
        timestamps = tuple(event.timestamp for event in train_events)
        seen.append(timestamps)
        return lambda event: event.match

    result = walk_forward_validate(
        events,
        lambda e: False,
        lambda e: e.value,
        initial_train_size=100,
        validation_size=50,
        test_size=50,
        step_size=50,
        min_test_events=20,
        fit_callback=fit,
    )

    assert result.fit_mode == "train_only_fit"
    assert len(seen) == result.total_folds
    for timestamps, fold in zip(seen, result.folds):
        assert timestamps
        assert max(timestamps) < events[100].timestamp if fold.fold == 0 else True
        assert all(ts < events[100 + fold.fold * 50].timestamp for ts in timestamps)
        assert all(
            ts not in {e.timestamp for e in events[100 + fold.fold * 50 : 200 + fold.fold * 50]}
            for ts in timestamps
        )


def test_train_only_fit_uses_purged_train_partition():
    events = _events(240)
    seen: list[tuple[datetime, ...]] = []

    def fit(train_events):
        seen.append(tuple(event.timestamp for event in train_events))
        return lambda event: True

    result = walk_forward_validate(
        events,
        lambda e: False,
        lambda e: e.value,
        initial_train_size=100,
        validation_size=40,
        test_size=40,
        step_size=40,
        min_test_events=20,
        purge_days=3,
        max_outcome_horizon_days=3,
        fit_callback=fit,
    )

    assert result.fit_mode == "train_only_fit"
    assert result.total_folds == 2
    for fold_index, timestamps in enumerate(seen):
        validation_start = events[100 + fold_index * 40].timestamp
        assert max(timestamps) < validation_start - timedelta(days=3)


def test_fit_callback_must_return_callable_matcher():
    with pytest.raises(TypeError, match="callable matcher"):
        walk_forward_validate(
            _events(220),
            lambda e: True,
            lambda e: e.value,
            initial_train_size=100,
            validation_size=40,
            test_size=40,
            fit_callback=lambda train: object(),
        )


def test_legacy_fixed_matcher_api_remains_compatible():
    result = walk_forward_validate(
        _events(220),
        lambda e: e.match,
        lambda e: e.value,
        initial_train_size=100,
        validation_size=40,
        test_size=40,
        step_size=40,
    )
    assert result.total_folds == 2
    assert result.fit_mode == "fixed_matcher"


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("initial_train_size", True),
        ("validation_size", 1.5),
        ("test_size", False),
        ("step_size", 2.5),
        ("min_test_events", True),
        ("purge_days", True),
        ("embargo_days", 0.5),
        ("max_outcome_horizon_days", False),
        ("confidence_level", True),
        ("confidence_level", float("nan")),
    ],
)
def test_invalid_walk_forward_parameters_fail_closed(parameter, value):
    kwargs = {
        "initial_train_size": 40,
        "validation_size": 20,
        "test_size": 20,
        "step_size": 20,
        "min_test_events": 10,
    }
    kwargs[parameter] = value
    with pytest.raises(ValueError):
        walk_forward_validate(
            _events(100),
            lambda e: e.match,
            lambda e: e.value,
            **kwargs,
        )


def test_walk_forward_rejects_integer_confidence_level_that_overflows_float():
    with pytest.raises(ValueError, match="confidence_level must be finite"):
        walk_forward_validate(
            _events(100),
            lambda e: e.match,
            lambda e: e.value,
            initial_train_size=40,
            validation_size=20,
            test_size=20,
            step_size=20,
            confidence_level=10**1000,
        )


def test_walk_forward_rejects_outcome_integer_that_overflows_float():
    with pytest.raises(ValueError, match="matched outcome values must be finite numbers"):
        walk_forward_validate(
            _events(100),
            lambda e: e.match,
            lambda e: 10**1000,
            initial_train_size=40,
            validation_size=20,
            test_size=20,
            step_size=20,
        )
