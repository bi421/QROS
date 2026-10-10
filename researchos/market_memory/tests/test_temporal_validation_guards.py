"""Regression tests for fail-closed chronological split parameters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from researchos.market_memory.temporal_validation import (
    chronological_split,
    expanding_window_splits,
)


@dataclass(frozen=True)
class Event:
    timestamp: datetime


def _events(count: int = 10) -> list[Event]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [Event(start + timedelta(days=i)) for i in range(count)]


@pytest.mark.parametrize(
    ("train_ratio", "validation_ratio"),
    [
        (True, 0.2),
        (float("nan"), 0.2),
        (0.6, float("inf")),
        (0.8, 0.2),
        (0.6, -0.1),
    ],
)
def test_chronological_split_rejects_invalid_ratios(train_ratio, validation_ratio):
    with pytest.raises(ValueError):
        chronological_split(_events(), train_ratio, validation_ratio)


def test_chronological_split_rejects_unsorted_events():
    events = _events()
    events[0], events[1] = events[1], events[0]

    with pytest.raises(ValueError, match="sorted by timestamp"):
        chronological_split(events)


@pytest.mark.parametrize(
    ("initial_train_size", "validation_size", "step_size"),
    [
        (0, 2, 1),
        (2, 0, 1),
        (2, 1, 0),
        (True, 2, 1),
        (2, 1.5, 1),
    ],
)
def test_expanding_window_splits_rejects_invalid_window_sizes(
    initial_train_size, validation_size, step_size
):
    with pytest.raises(ValueError):
        expanding_window_splits(
            _events(), initial_train_size, validation_size, step_size
        )


def test_expanding_window_splits_rejects_unsorted_events():
    events = _events()
    events[0], events[1] = events[1], events[0]

    with pytest.raises(ValueError, match="sorted by timestamp"):
        expanding_window_splits(events, 2, 2, 1)


def test_expanding_window_splits_valid_configuration():
    splits = expanding_window_splits(_events(), 4, 2, 2)

    assert len(splits) == 3
    assert len(splits[0][0]) == 4
    assert len(splits[1][0]) == 6
    assert len(splits[2][0]) == 8
