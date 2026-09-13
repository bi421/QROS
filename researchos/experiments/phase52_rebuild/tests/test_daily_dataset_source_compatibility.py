from __future__ import annotations

from pathlib import Path

from researchos.experiments.phase52_rebuild.daily_dataset import load_daily_xau_from_m1


def test_canonical_d1_source_is_loaded_without_repair(tmp_path: Path) -> None:
    source = tmp_path / "xauusd_d1.csv"
    source.write_text(
        "Date,Time,Open,High,Low,Close,tick_volume\n"
        "2021.01.04,00:00:00,1900,1910,1890,1905,100\n"
        "2021.01.05,00:00:00,1905,1920,1900,1915,120\n",
        encoding="utf-8",
    )

    rows = load_daily_xau_from_m1(source)

    assert [row.day for row in rows] == ["2021-01-04", "2021-01-05"]
    assert rows[0].open == 1900.0
    assert rows[0].high == 1910.0
    assert rows[0].low == 1890.0
    assert rows[0].close == 1905.0
    assert rows[0].tick_volume == 100.0
    assert rows[0].spread is None
    assert rows[0].real_volume == 0.0
    assert rows[0].m1_rows == 0
    assert rows[0].vwap == (1910.0 + 1890.0 + 1905.0) / 3.0
