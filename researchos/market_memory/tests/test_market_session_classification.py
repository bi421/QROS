"""Regression tests for market-session classification boundaries."""

from datetime import datetime, timezone

import pytest

from researchos.market_memory.event_extractor import _determine_session


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (0, "Asian"),
        (7, "Asian"),
        (8, "European"),
        (11, "European"),
        (12, "Overlap"),
        (15, "Overlap"),
        (16, "US"),
        (20, "US"),
        (21, "US"),
        (23, "US"),
    ],
)
def test_determine_session_utc_boundaries(hour: int, expected: str) -> None:
    timestamp = datetime(2025, 1, 1, hour, tzinfo=timezone.utc)
    assert _determine_session(timestamp) == expected
