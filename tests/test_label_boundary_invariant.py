from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from researchos.market_memory.oos_validation import assert_label_boundaries


def _events():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        SimpleNamespace(timestamp=start + timedelta(days=i))
        for i in range(6)
    ]


def test_label_boundaries_are_inside_partitions():
    events = _events()
    train, validation, test = events[:2], events[2:4], events[4:]

    assert_label_boundaries(
        train,
        validation,
        test,
        lambda event: event.timestamp + timedelta(hours=12),
    )


def test_train_label_crossing_validation_boundary_is_rejected():
    events = _events()
    train, validation, test = events[:2], events[2:4], events[4:]

    with pytest.raises(ValueError, match="train label extends into validation"):
        assert_label_boundaries(
            train,
            validation,
            test,
            lambda event: validation[0].timestamp + timedelta(minutes=1)
            if event is train[-1]
            else event.timestamp + timedelta(hours=1),
        )


def test_validation_label_crossing_test_boundary_is_rejected():
    events = _events()
    train, validation, test = events[:2], events[2:4], events[4:]

    with pytest.raises(ValueError, match="validation label extends into test"):
        assert_label_boundaries(
            train,
            validation,
            test,
            lambda event: test[0].timestamp + timedelta(minutes=1)
            if event is validation[-1]
            else event.timestamp + timedelta(hours=1),
        )


@pytest.mark.parametrize(
    ("empty_partition", "expected_name"),
    [
        ("train", "train"),
        ("validation", "validation"),
        ("test", "test"),
    ],
)
def test_label_boundary_audit_rejects_empty_partition(empty_partition, expected_name):
    events = _events()
    partitions = {
        "train": events[:2],
        "validation": events[2:4],
        "test": events[4:],
    }
    partitions[empty_partition] = []

    with pytest.raises(ValueError, match=rf"empty: .*{expected_name}"):
        assert_label_boundaries(
            partitions["train"],
            partitions["validation"],
            partitions["test"],
            lambda event: event.timestamp + timedelta(hours=1),
        )
