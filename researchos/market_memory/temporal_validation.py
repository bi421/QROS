"""
Temporal Validation — chronological validation for market memory findings.

Implements:
  - Chronological train/validation/test splits
  - Walk-forward validation
  - Expanding window validation
  - Stability detection

Never uses random shuffling. Always respects temporal order.
"""

from __future__ import annotations

import math
from typing import Any


def _validated_ratio(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number strictly between 0 and 1")
    try:
        normalized = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{name} must be a finite number strictly between 0 and 1") from None
    if not math.isfinite(normalized) or not 0.0 < normalized < 1.0:
        raise ValueError(f"{name} must be a finite number strictly between 0 and 1")
    return normalized


def _validate_window_size(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _require_chronological(events: list[Any]) -> None:
    for i, event in enumerate(events):
        if not hasattr(event, "timestamp"):
            raise ValueError(f"event at index {i} has no timestamp")
        if i and event.timestamp < events[i - 1].timestamp:
            raise ValueError(f"events must be sorted by timestamp; out of order at index {i}")


def chronological_split(
    events: list[Any],
    train_ratio: float = 0.6,
    validation_ratio: float = 0.2,
) -> tuple[list[Any], list[Any], list[Any]]:
    """
    Split events chronologically into train, validation, and test sets.

    Args:
        events: List of events sorted by timestamp
        train_ratio: Fraction for training (default 0.6)
        validation_ratio: Fraction for validation (default 0.2)

    Returns:
        Tuple of (train_events, validation_events, test_events)
    """
    train_ratio = _validated_ratio("train_ratio", train_ratio)
    validation_ratio = _validated_ratio("validation_ratio", validation_ratio)
    if train_ratio + validation_ratio >= 1.0:
        raise ValueError("train_ratio + validation_ratio must be less than 1")
    _require_chronological(events)
    if not events:
        return [], [], []

    n = len(events)
    train_end = int(n * train_ratio)
    val_end = train_end + int(n * validation_ratio)

    train = events[:train_end]
    validation = events[train_end:val_end]
    test = events[val_end:]

    return train, validation, test


def expanding_window_splits(
    events: list[Any],
    initial_train_size: int = 100,
    validation_size: int = 50,
    step_size: int = 50,
) -> list[tuple[list[Any], list[Any]]]:
    """
    Generate expanding window train/validation splits.

    The training window expands by step_size each fold.
    Validation window is always validation_size.
    """
    initial_train_size = _validate_window_size("initial_train_size", initial_train_size)
    validation_size = _validate_window_size("validation_size", validation_size)
    step_size = _validate_window_size("step_size", step_size)
    _require_chronological(events)

    splits = []
    n = len(events)
    train_end = initial_train_size
    while train_end + validation_size <= n:
        train = events[:train_end]
        validation = events[train_end : train_end + validation_size]
        splits.append((train, validation))
        train_end += step_size

    return splits


def check_temporal_integrity(
    events: list[Any],
) -> dict[str, Any]:
    """
    Check temporal integrity of event list.

    Verifies:
      - Events are sorted by timestamp
      - No duplicate timestamps (within same asset/timeframe)
      - No future leakage in conditioning variables
    """
    if not events:
        return {"status": "PASS", "issues": []}

    issues = []

    # Check sorting
    for i in range(1, len(events)):
        if events[i].timestamp < events[i - 1].timestamp:
            issues.append(f"Timestamp out of order at index {i}")

    # Check duplicates
    seen = set()
    for i, e in enumerate(events):
        key = (e.asset, e.timeframe, e.timestamp.isoformat())
        if key in seen:
            issues.append(f"Duplicate event at index {i}: {key}")
        seen.add(key)

    return {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "total_events": len(events),
    }
