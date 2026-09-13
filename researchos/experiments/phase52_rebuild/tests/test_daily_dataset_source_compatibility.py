from __future__ import annotations

from pathlib import Path

import pytest

from researchos.experiments.phase52_rebuild.daily_dataset import load_daily_xau_from_m1


def test_canonical_d1_source_requires_explicit_vwap(tmp_path: Path) -> None:
    source = tmp_path / "xauusd_d1.csv"
    source.write_text(
        "Date,Time,Open,High,Low,Close,tick_volume\n"
        "2021.01.04,00:00:00,1900,1910,1890,1905,100\n"
        "2021.01.05,00:00:00,1905,1920,1900,1915,120\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=r"canonical D1 source must contain Date/Time/OHLC/tick_volume/vwap schema",
    ):
        load_daily_xau_from_m1(source)


def test_canonical_d1_vwap_is_preserved_without_recomputation(tmp_path: Path) -> None:
    source = tmp_path / "xauusd_d1.csv"
    source.write_text(
        "Date,Time,Open,High,Low,Close,tick_volume,vwap\n"
        "2021.01.04,00:00:00,1900,1910,1890,1905,100,1901.25\n"
        "2021.01.05,00:00:00,1905,1920,1900,1915,120,1911.75\n",
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
    assert rows[0].vwap == 1901.25


def test_m1_and_d1_paths_produce_identical_true_vwap(tmp_path: Path) -> None:
    m1 = tmp_path / "xauusd_m1.csv"
    m1.write_text(
        "time,open,high,low,close,tick_volume,spread,real_volume\n"
        "2021-01-04T00:00:00Z,1900,1910,1890,1905,100,1,0\n"
        "2021-01-04T00:01:00Z,1905,1920,1900,1915,300,1,0\n",
        encoding="utf-8",
    )
    expected_vwap = (((1910 + 1890 + 1905) / 3.0) * 100 + ((1920 + 1900 + 1915) / 3.0) * 300) / 400

    m1_rows = load_daily_xau_from_m1(m1)
    assert m1_rows[0].vwap == pytest.approx(expected_vwap)

    d1 = tmp_path / "xauusd_d1.csv"
    d1.write_text(
        "Date,Time,Open,High,Low,Close,tick_volume,vwap\n"
        f"2021.01.04,00:00:00,1900,1920,1890,1915,400,{expected_vwap}\n",
        encoding="utf-8",
    )

    d1_rows = load_daily_xau_from_m1(d1)
    assert d1_rows[0].vwap == pytest.approx(m1_rows[0].vwap)
