"""Realized-label overlap and dependence diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol, Sequence, TypeVar


class _TimestampedEvent(Protocol):
    @property
    def timestamp(self) -> datetime: ...


EventT = TypeVar("EventT", bound=_TimestampedEvent)


@dataclass(frozen=True)
class LabelOverlapAudit:
    """Deterministic pairwise overlap audit for event label windows."""

    total_events: int
    events_with_realized_end: int
    missing_realized_end: int
    overlap_pairs: int
    max_concurrent_labels: int

    @property
    def passed(self) -> bool:
        return self.missing_realized_end == 0


def audit_label_overlap(
    events: Sequence[EventT],
    label_end_getter: Callable[[EventT], datetime | None],
) -> LabelOverlapAudit:
    """Measure dependence caused by overlapping realized outcome windows.

    Intervals are half-open [event_timestamp, realized_end). A shared boundary
    is therefore not counted as overlap; an actual intersection is.
    """
    intervals: list[tuple[datetime, datetime]] = []
    missing = 0
    for event in events:
        start = event.timestamp
        end = label_end_getter(event)
        if end is None:
            missing += 1
            continue
        if end <= start:
            raise ValueError("realized label end must be after event timestamp")
        intervals.append((start, end))

    intervals.sort(key=lambda item: (item[0], item[1]))
    active: list[datetime] = []
    overlap_pairs = 0
    max_concurrent = 0
    for start, end in intervals:
        active = [active_end for active_end in active if active_end > start]
        overlap_pairs += len(active)
        active.append(end)
        max_concurrent = max(max_concurrent, len(active))

    return LabelOverlapAudit(
        total_events=len(events),
        events_with_realized_end=len(intervals),
        missing_realized_end=missing,
        overlap_pairs=overlap_pairs,
        max_concurrent_labels=max_concurrent,
    )


__all__ = ["LabelOverlapAudit", "audit_label_overlap"]
