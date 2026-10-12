"""Latency and freshness contracts for time-sensitive XAUUSD research.

This module is deliberately additive: it does not alter engine mathematics,
fetch market data, execute orders, or assume that wall-clock latency can be zero.
Use source timestamps for freshness and a monotonic clock for elapsed processing time.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class LatencyStatus(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


@dataclass(frozen=True)
class LatencyPolicy:
    """Per-source latency limits; configure these from measured feed behavior."""

    max_source_age_ms: float
    max_future_skew_ms: float = 100.0
    max_processing_ms: float = 100.0

    def __post_init__(self) -> None:
        for name, value in (
            ("max_source_age_ms", self.max_source_age_ms),
            ("max_future_skew_ms", self.max_future_skew_ms),
            ("max_processing_ms", self.max_processing_ms),
        ):
            if isinstance(value, bool):
                raise ValueError(f"{name} must be a finite number")
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"{name} must be a finite number") from exc
            if not math.isfinite(number):
                raise ValueError(f"{name} must be a finite number")
            if name == "max_source_age_ms" and number <= 0:
                raise ValueError(f"{name} must be positive")
            if name != "max_source_age_ms" and number < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, number)


@dataclass(frozen=True)
class LatencyAssessment:
    """Auditable gate decision; REJECT means do not consume the input."""

    status: LatencyStatus
    source_age_ms: float | None
    processing_ms: float | None
    reason_codes: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return self.status is LatencyStatus.ACCEPT


def start_monotonic_timer() -> int:
    """Capture a monotonic nanosecond tick before work begins."""
    return time.perf_counter_ns()


def elapsed_ns(started_ns: int, ended_ns: int | None = None) -> int:
    """Return monotonic elapsed nanoseconds; reject invalid or reversed ticks."""
    if isinstance(started_ns, bool) or not isinstance(started_ns, int) or started_ns < 0:
        raise ValueError("started_ns must be a non-negative integer")
    end = time.perf_counter_ns() if ended_ns is None else ended_ns
    if isinstance(end, bool) or not isinstance(end, int) or end < started_ns:
        raise ValueError("ended_ns must be an integer not earlier than started_ns")
    return end - started_ns


class LatencyGate:
    """Fail-closed source freshness and compute-budget gate."""

    def __init__(self, policy: LatencyPolicy) -> None:
        self._policy = policy

    def assess(
        self,
        *,
        source_as_of: datetime,
        evaluated_at: datetime,
        processing_ns: int,
    ) -> LatencyAssessment:
        reasons: list[str] = []
        age_ms: float | None = None
        processing_ms: float | None = None

        for value, name in ((source_as_of, "source_as_of"), (evaluated_at, "evaluated_at")):
            if (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                reasons.append(f"INVALID_{name.upper()}_TIMEZONE")

        if not reasons:
            age_ms = (evaluated_at - source_as_of).total_seconds() * 1000.0
            if age_ms < -self._policy.max_future_skew_ms:
                reasons.append("SOURCE_TIMESTAMP_IN_FUTURE")
            elif age_ms > self._policy.max_source_age_ms:
                reasons.append("SOURCE_DATA_STALE")
            age_ms = max(0.0, age_ms)

        if (
            isinstance(processing_ns, bool)
            or not isinstance(processing_ns, int)
            or processing_ns < 0
        ):
            reasons.append("INVALID_PROCESSING_DURATION")
        else:
            processing_ms = processing_ns / 1_000_000.0
            if processing_ms > self._policy.max_processing_ms:
                reasons.append("PROCESSING_BUDGET_EXCEEDED")

        unique_reasons = tuple(sorted(set(reasons)))
        return LatencyAssessment(
            status=LatencyStatus.REJECT if unique_reasons else LatencyStatus.ACCEPT,
            source_age_ms=age_ms,
            processing_ms=processing_ms,
            reason_codes=unique_reasons,
        )


__all__ = [
    "LatencyAssessment",
    "LatencyGate",
    "LatencyPolicy",
    "LatencyStatus",
    "elapsed_ns",
    "start_monotonic_timer",
]
