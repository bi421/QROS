"""Fail-closed sequence integrity checks for replayed market events.

This guard is deliberately separate from feature calculations and feed adapters.
It evaluates events in ingestion order, per source. A missing, duplicate,
regressing, or skipped sequence means the caller cannot claim a complete stream.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from researchos.orchestration.market_state_reconstruction import EventClock


@dataclass(frozen=True)
class SequenceIntegrityReport:
    """Auditable result; sequence gaps are not silently repaired."""

    valid: bool
    event_count: int
    source_count: int
    issue_codes: tuple[str, ...]
    source_issue_codes: tuple[tuple[str, str], ...]


def assess_sequence_integrity(
    events: Sequence[EventClock],
) -> SequenceIntegrityReport:
    """Require positive, strictly increasing, gap-free sequences per source.

    Input order is ingestion order and must be preserved. Sequence counters may
    start at any positive value and are independent across sources. Event-time
    ordering is intentionally not enforced here because late-arriving events
    can be legitimate; consumers must separately enforce point-in-time cutoffs.
    """
    if isinstance(events, (str, bytes)):
        raise TypeError("events must be a sequence of EventClock values")

    seen_sources: set[str] = set()
    last_sequence: dict[str, int] = {}
    issues: set[str] = set()
    source_issues: set[tuple[str, str]] = set()

    for index, event in enumerate(events):
        if not isinstance(event, EventClock):
            raise TypeError(f"event at index {index} must be EventClock")
        event.validate()
        source = event.source.strip()
        seen_sources.add(source)
        sequence = event.sequence
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
            issues.add("SEQUENCE_MISSING_OR_INVALID")
            source_issues.add((source, "SEQUENCE_MISSING_OR_INVALID"))
            continue

        previous = last_sequence.get(source)
        if previous is not None:
            if sequence == previous:
                code = "SEQUENCE_DUPLICATE"
            elif sequence < previous:
                code = "SEQUENCE_REGRESSION"
            elif sequence > previous + 1:
                code = "SEQUENCE_GAP"
            else:
                last_sequence[source] = sequence
                continue
            issues.add(code)
            source_issues.add((source, code))
        last_sequence[source] = sequence

    return SequenceIntegrityReport(
        valid=not issues,
        event_count=len(events),
        source_count=len(seen_sources),
        issue_codes=tuple(sorted(issues)),
        source_issue_codes=tuple(sorted(source_issues)),
    )


__all__ = ["SequenceIntegrityReport", "assess_sequence_integrity"]
