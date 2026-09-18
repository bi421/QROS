"""Regression tests for strict real-data loading."""

from __future__ import annotations

import pandas as pd
import pytest

from researchos.data_engine.real_data_loader import _parse_utc_dates


def test_epoch_milliseconds_are_parsed_as_milliseconds():
    values = pd.Series([1609718400000, 1609804800000])
    parsed = _parse_utc_dates(values, "dxy.csv")
    assert parsed.tolist() == [
        pd.Timestamp("2021-01-04", tz="UTC"),
        pd.Timestamp("2021-01-05", tz="UTC"),
    ]


def test_epoch_seconds_are_parsed_as_seconds():
    values = pd.Series([1609718400, 1609804800])
    parsed = _parse_utc_dates(values, "series.csv")
    assert parsed.tolist() == [
        pd.Timestamp("2021-01-04", tz="UTC"),
        pd.Timestamp("2021-01-05", tz="UTC"),
    ]


def test_iso_dates_are_normalized_to_utc_calendar_days():
    values = pd.Series(["2021-01-04T18:30:00-05:00", "2021-01-05"])
    parsed = _parse_utc_dates(values, "series.csv")
    assert parsed.tolist() == [
        pd.Timestamp("2021-01-04", tz="UTC"),
        pd.Timestamp("2021-01-05", tz="UTC"),
    ]


def test_mixed_timestamp_formats_fail_closed():
    values = pd.Series([1609718400000, "2021-01-05"])
    with pytest.raises(ValueError, match="mixed numeric/non-numeric"):
        _parse_utc_dates(values, "series.csv")
