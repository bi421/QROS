from __future__ import annotations

import pandas as pd
import pytest

from researchos.experiments.phase52.alignment import validate_exact_timestamp_alignment
from researchos.experiments.phase52.scripts.run_phase52_experiment import _build_common_observation_sample, _load_candles


def ts(*values: str) -> list[pd.Timestamp]:
    return [pd.Timestamp(value, tz="UTC") for value in values]


def test_exact_timestamp_alignment_passes() -> None:
    values = ts("2025-01-02 00:00", "2025-01-03 00:00")
    validate_exact_timestamp_alignment(values, values, "DXY")


def test_shifted_timestamp_blocks() -> None:
    with pytest.raises(ValueError, match="exact timestamp mismatch"):
        validate_exact_timestamp_alignment(
            ts("2025-01-02 00:00", "2025-01-03 00:00"),
            ts("2025-01-02 00:00", "2025-01-03 00:01"),
            "DXY",
        )


def test_missing_timestamp_blocks() -> None:
    with pytest.raises(ValueError, match="timestamp length mismatch"):
        validate_exact_timestamp_alignment(
            ts("2025-01-02 00:00", "2025-01-03 00:00"),
            ts("2025-01-02 00:00"),
            "US10Y",
        )


def test_duplicate_timestamp_blocks() -> None:
    with pytest.raises(ValueError, match="duplicate timestamps"):
        validate_exact_timestamp_alignment(
            ts("2025-01-02 00:00", "2025-01-03 00:00"),
            ts("2025-01-02 00:00", "2025-01-02 00:00"),
            "VIX",
        )


def test_reordered_timestamp_blocks() -> None:
    with pytest.raises(ValueError, match="exact timestamp mismatch"):
        validate_exact_timestamp_alignment(
            ts("2025-01-02 00:00", "2025-01-03 00:00"),
            ts("2025-01-03 00:00", "2025-01-02 00:00"),
            "DXY",
        )


def test_common_observation_sample_excludes_calendar_gaps_without_repair() -> None:
    timestamps = ts("2025-01-02 00:00", "2025-01-03 00:00", "2025-01-06 00:00")
    macro_ts = {
        "DXY": ts("2025-01-02 00:00", "2025-01-03 00:00", "2025-01-06 00:00"),
        "US10Y": ts("2025-01-02 00:00", "2025-01-06 00:00"),
        "VIX": ts("2025-01-02 00:00", "2025-01-03 00:00", "2025-01-06 00:00"),
    }
    macro = {
        "DXY": [100.0, 101.0, 102.0],
        "US10Y": [4.0, 4.2],
        "VIX": [15.0, 16.0, 17.0],
    }

    result = _build_common_observation_sample(
        [1900.0, 1910.0, 1920.0],
        [1910.0, 1920.0, 1930.0],
        [1890.0, 1900.0, 1910.0],
        [100.0, 110.0, 120.0],
        timestamps,
        macro,
        macro_ts,
        ("DXY", "US10Y", "VIX"),
    )

    close, _, _, _, common_ts, filtered_macro, filtered_macro_ts = result
    assert close == [1900.0, 1920.0]
    assert common_ts == timestamps[::2]
    assert filtered_macro["DXY"] == [100.0, 102.0]
    assert filtered_macro["US10Y"] == [4.0, 4.2]
    assert filtered_macro["VIX"] == [15.0, 17.0]
    assert filtered_macro_ts["US10Y"] == common_ts


def test_common_observation_sample_rejects_duplicate_macro_timestamps() -> None:
    timestamps = ts("2025-01-02 00:00", "2025-01-03 00:00")
    macro_ts = {
        "DXY": timestamps,
        "US10Y": ts("2025-01-02 00:00", "2025-01-02 00:00"),
        "VIX": timestamps,
    }
    macro = {"DXY": [100.0, 101.0], "US10Y": [4.0, 4.1], "VIX": [15.0, 16.0]}

    with pytest.raises(ValueError, match="US10Y: duplicate calendar days"):
        _build_common_observation_sample(
            [1900.0, 1910.0],
            [1910.0, 1920.0],
            [1890.0, 1900.0],
            [100.0, 110.0],
            timestamps,
            macro,
            macro_ts,
            ("DXY", "US10Y", "VIX"),
        )


def test_common_observation_sample_aligns_same_utc_calendar_day_with_different_time() -> None:
    timestamps = ts("2025-01-02 00:00", "2025-01-03 00:00")
    macro_ts = {
        "DXY": ts("2025-01-02 22:00", "2025-01-03 22:00"),
        "US10Y": ts("2025-01-02 00:00", "2025-01-03 00:00"),
        "VIX": ts("2025-01-02 00:00", "2025-01-03 00:00"),
    }
    macro = {
        "DXY": [100.0, 101.0],
        "US10Y": [4.0, 4.1],
        "VIX": [15.0, 16.0],
    }

    result = _build_common_observation_sample(
        [1900.0, 1910.0],
        [1910.0, 1920.0],
        [1890.0, 1900.0],
        [100.0, 110.0],
        timestamps,
        macro,
        macro_ts,
        ("DXY", "US10Y", "VIX"),
    )

    _, _, _, _, common_ts, filtered_macro, filtered_macro_ts = result
    assert common_ts == timestamps
    assert filtered_macro["DXY"] == [100.0, 101.0]
    assert filtered_macro_ts["DXY"] == common_ts


def test_common_observation_sample_rejects_duplicate_macro_calendar_day() -> None:
    timestamps = ts("2025-01-02 00:00")
    macro_ts = {
        "DXY": ts("2025-01-02 10:00", "2025-01-02 22:00"),
        "US10Y": timestamps,
        "VIX": timestamps,
    }
    macro = {"DXY": [100.0, 101.0], "US10Y": [4.0], "VIX": [15.0]}

    with pytest.raises(ValueError, match="DXY: duplicate calendar days"):
        _build_common_observation_sample(
            [1900.0],
            [1910.0],
            [1890.0],
            [100.0],
            timestamps,
            macro,
            macro_ts,
            ("DXY", "US10Y", "VIX"),
        )

def test_load_candles_aggregates_canonical_m1_to_daily() -> None:
    import csv

    rows = [
        ["2025-01-02T00:01:00Z", "1900", "1910", "1890", "1905", "10", "2", "0"],
        ["2025-01-02T00:02:00Z", "1905", "1920", "1900", "1915", "20", "4", "0"],
        ["2025-01-03T00:01:00Z", "1915", "1930", "1910", "1925", "30", "6", "0"],
    ]

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "xau.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"])
            writer.writerows(rows)

        close, high, low, volume, timestamps = _load_candles(
            str(path), "auto", "XAUUSD", "1d"
        )

    assert close == [1915.0, 1925.0]
    assert high == [1920.0, 1930.0]
    assert low == [1890.0, 1910.0]
    assert volume == [30.0, 30.0]
    assert [str(ts) for ts in timestamps] == [
        "2025-01-02T00:00:00+00:00",
        "2025-01-03T00:00:00+00:00",
    ]
