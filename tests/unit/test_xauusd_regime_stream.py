from pathlib import Path

import pandas as pd
import pytest

from scripts.run_xauusd_regime_stream import process_csv


def test_stream_processor_reads_mt5_date_time_csv_in_chunks(tmp_path: Path):
    source = tmp_path / "mt5.csv"
    pd.DataFrame(
        {
            "<DATE>": ["2026.01.01"] * 4,
            "<TIME>": ["00:00:00", "01:00:00", "02:00:00", "03:00:00"],
            "<HIGH>": [2002, 2003, 2004, 2005],
            "<LOW>": [1998, 1999, 2000, 2001],
            "<CLOSE>": [2000, 2001, 2002, 2003],
        }
    ).to_csv(source, index=False)

    result = process_csv(source, chunksize=2, lookback=40, adx_period=5)

    assert result["input"]["row_count"] == 4
    assert result["input"]["memory_map_enabled"] is True
    assert result["input"]["sha256"]
    assert result["result"]["status"] == "INSUFFICIENT_EVIDENCE"


def test_stream_processor_rejects_duplicate_timestamps_across_chunks(tmp_path: Path):
    source = tmp_path / "duplicate.csv"
    pd.DataFrame(
        {
            "timestamp": [
                "2026-01-01T00:00:00Z",
                "2026-01-01T01:00:00Z",
                "2026-01-01T01:00:00Z",
            ],
            "high": [2002, 2003, 2004],
            "low": [1998, 1999, 2000],
            "close": [2000, 2001, 2002],
        }
    ).to_csv(source, index=False)

    with pytest.raises(ValueError, match="duplicate or not chronological"):
        process_csv(source, chunksize=2, lookback=40, adx_period=5)
