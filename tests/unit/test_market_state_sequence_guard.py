"""Regression tests for fail-closed source sequence integrity."""
import pytest

from researchos.orchestration.market_state_reconstruction import EventClock
from researchos.orchestration.market_state_sequence_guard import (
    assess_sequence_integrity,
)


def event(source: str, sequence: int | None, offset: int = 0) -> EventClock:
    timestamp = 1_800_000_000_000_000_000 + offset
    return EventClock(source, timestamp, timestamp + 1, sequence)


def test_independent_sources_can_have_independent_gap_free_sequences():
    report = assess_sequence_integrity(
        [event("broker", 12), event("COMEX", 3), event("broker", 13), event("COMEX", 4)]
    )
    assert report.valid is True
    assert report.event_count == 4
    assert report.source_count == 2
    assert report.issue_codes == ()


@pytest.mark.parametrize(
    ("sequences", "expected"),
    [
        ([7, 7], "SEQUENCE_DUPLICATE"),
        ([7, 6], "SEQUENCE_REGRESSION"),
        ([7, 9], "SEQUENCE_GAP"),
        ([7, None], "SEQUENCE_MISSING_OR_INVALID"),
        ([7, 0], "SEQUENCE_MISSING_OR_INVALID"),
    ],
)
def test_duplicate_regressing_gapped_or_missing_sequence_fails_closed(sequences, expected):
    report = assess_sequence_integrity(
        [event("COMEX", sequence, offset=index) for index, sequence in enumerate(sequences)]
    )
    assert report.valid is False
    assert expected in report.issue_codes
    assert ("COMEX", expected) in report.source_issue_codes


def test_sequence_guard_does_not_confuse_late_event_time_with_sequence_regression():
    late = event("COMEX", 10, offset=20)
    newer = event("COMEX", 11, offset=10)
    report = assess_sequence_integrity([late, newer])
    assert report.valid is True


def test_rejects_non_event_input():
    with pytest.raises(TypeError, match="EventClock"):
        assess_sequence_integrity([object()])
