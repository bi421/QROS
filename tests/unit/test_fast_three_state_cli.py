import csv

from scripts.run_fast_three_state import classify_csv


def write_csv(path, closes):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Close"])
        for index, close in enumerate(closes):
            writer.writerow([f"2026-01-{index + 1:02d}", close])


def test_csv_cli_returns_one_of_three_names_for_uptrend(tmp_path):
    source = tmp_path / "up.csv"
    write_csv(source, [2000 + index for index in range(40)])
    assert classify_csv(source, lookback=8, min_move_bps=0) == "UP"


def test_csv_cli_returns_range_during_warmup(tmp_path):
    source = tmp_path / "short.csv"
    write_csv(source, [2000, 2001, 2000])
    assert classify_csv(source, lookback=8) == "RANGE"


def test_csv_cli_returns_one_of_three_names_for_downtrend(tmp_path):
    source = tmp_path / "down.csv"
    write_csv(source, [2000 - index for index in range(40)])
    assert classify_csv(source, lookback=8, min_move_bps=0) == "DOWN"
