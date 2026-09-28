from __future__ import annotations

from scripts.audit_phase52_timestamp_overlap import audit_overlap


def test_audit_overlap_distinguishes_exact_timestamp_and_calendar_date() -> None:
    price = [
        "2024-01-02T00:00:00+00:00",
        "2024-01-03T00:00:00+00:00",
        "2024-01-04T00:00:00+00:00",
    ]
    macro = {
        "DXY": [
            "2024-01-02T12:00:00+00:00",
            "2024-01-03T12:00:00+00:00",
            "2024-01-04T12:00:00+00:00",
        ],
        "US10Y": [
            "2024-01-02T00:00:00+00:00",
            "2024-01-03T00:00:00+00:00",
            "2024-01-04T00:00:00+00:00",
        ],
        "VIX": [
            "2024-01-02T00:00:00+00:00",
            "2024-01-03T00:00:00+00:00",
            "2024-01-04T00:00:00+00:00",
        ],
    }

    report = audit_overlap(price, macro)

    assert report["exact_timestamp_common"] == 0
    assert report["calendar_date_common"] == 3
    assert report["date_only_gap_vs_exact"] == 3
    assert report["diagnostic_boundary"].startswith("Calendar-date overlap is diagnostic only")


def test_audit_overlap_reports_exact_common_sample() -> None:
    price = [
        "2024-01-02T00:00:00+00:00",
        "2024-01-03T00:00:00+00:00",
        "2024-01-04T00:00:00+00:00",
    ]
    macro = {
        "DXY": price,
        "US10Y": price,
        "VIX": price,
    }

    report = audit_overlap(price, macro)

    assert report["exact_timestamp_common"] == 3
    assert report["calendar_date_common"] == 3
    assert report["date_only_gap_vs_exact"] == 0
