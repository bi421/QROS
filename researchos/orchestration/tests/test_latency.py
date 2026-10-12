"""Regression tests for fail-closed latency and freshness gates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from researchos.orchestration.latency import (
    LatencyGate,
    LatencyPolicy,
    LatencyStatus,
    elapsed_ns,
)


UTC = timezone.utc


def test_fresh_source_within_compute_budget_is_accepted() -> None:
    now = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
    result = LatencyGate(LatencyPolicy(max_source_age_ms=500)).assess(
        source_as_of=now - timedelta(milliseconds=125),
        evaluated_at=now,
        processing_ns=12_000_000,
    )

    assert result.status is LatencyStatus.ACCEPT
    assert result.accepted
    assert result.source_age_ms == pytest.approx(125.0)
    assert result.processing_ms == pytest.approx(12.0)
    assert result.reason_codes == ()


def test_stale_source_fails_closed() -> None:
    now = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
    result = LatencyGate(LatencyPolicy(max_source_age_ms=100)).assess(
        source_as_of=now - timedelta(milliseconds=101),
        evaluated_at=now,
        processing_ns=1_000_000,
    )

    assert result.status is LatencyStatus.REJECT
    assert result.reason_codes == ("SOURCE_DATA_STALE",)


def test_future_source_beyond_clock_skew_fails_closed() -> None:
    now = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
    result = LatencyGate(
        LatencyPolicy(max_source_age_ms=500, max_future_skew_ms=20)
    ).assess(
        source_as_of=now + timedelta(milliseconds=21),
        evaluated_at=now,
        processing_ns=1_000_000,
    )

    assert result.status is LatencyStatus.REJECT
    assert result.reason_codes == ("SOURCE_TIMESTAMP_IN_FUTURE",)


def test_small_future_skew_is_clamped_to_zero_age() -> None:
    now = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
    result = LatencyGate(
        LatencyPolicy(max_source_age_ms=500, max_future_skew_ms=20)
    ).assess(
        source_as_of=now + timedelta(milliseconds=10),
        evaluated_at=now,
        processing_ns=1_000_000,
    )

    assert result.status is LatencyStatus.ACCEPT
    assert result.source_age_ms == 0.0


def test_processing_budget_exceeded_fails_closed() -> None:
    now = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
    result = LatencyGate(
        LatencyPolicy(max_source_age_ms=500, max_processing_ms=5)
    ).assess(
        source_as_of=now,
        evaluated_at=now,
        processing_ns=5_000_001,
    )

    assert result.status is LatencyStatus.REJECT
    assert result.reason_codes == ("PROCESSING_BUDGET_EXCEEDED",)


def test_naive_datetime_fails_closed() -> None:
    now = datetime(2026, 10, 12, 9, 0)
    result = LatencyGate(LatencyPolicy(max_source_age_ms=500)).assess(
        source_as_of=now,
        evaluated_at=now,
        processing_ns=0,
    )

    assert result.status is LatencyStatus.REJECT
    assert "INVALID_SOURCE_AS_OF_TIMEZONE" in result.reason_codes
    assert "INVALID_EVALUATED_AT_TIMEZONE" in result.reason_codes


@pytest.mark.parametrize(
    ("max_age", "future_skew", "processing"),
    [(0, 0, 1), (-1, 0, 1), (float("nan"), 0, 1), (1, -1, 1), (1, 0, float("inf"))],
)
def test_invalid_policy_budgets_are_rejected(
    max_age: float, future_skew: float, processing: float
) -> None:
    with pytest.raises(ValueError):
        LatencyPolicy(
            max_source_age_ms=max_age,
            max_future_skew_ms=future_skew,
            max_processing_ms=processing,
        )


def test_elapsed_ns_rejects_reversed_clock_ticks() -> None:
    assert elapsed_ns(100, 250) == 150
    with pytest.raises(ValueError, match="not earlier"):
        elapsed_ns(250, 100)
