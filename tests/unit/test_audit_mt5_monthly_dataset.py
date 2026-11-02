from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from scripts.audit_mt5_monthly_dataset import audit_dataset

BASE_EPOCH = 1_609_459_200
FIELDS = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]


def make_dataset(root: Path, rows: list[dict[str, int | float]]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    file_path = root / "XAUUSD_M1_2021_01.csv"
    with file_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    raw_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
    manifest = {
        "source": "MetaTrader5",
        "symbol": "XAUUSD",
        "timeframe": "M1",
        "requested_start": "2021-01-01T00:00:00+00:00",
        "requested_end": "2021-01-01T00:10:00+00:00",
        "terminal": {"version": 6292, "maxbars": 5_000_000},
        "symbol_metadata": {"digits": 2, "point": 0.01, "trade_contract_size": 100.0},
        "chunks": [{
            "file": "data/raw/mt5/ftmo_demo_xauusd_2021_2026/XAUUSD_M1_2021_01.csv",
            "sha256": raw_hash,
            "rows": len(rows),
            "first_epoch": int(rows[0]["time"]),
            "last_epoch": int(rows[-1]["time"]),
        }],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "source_context.json").write_text(json.dumps({"account_server": "FTMO-Demo"}), encoding="utf-8")
    return root


def valid_rows() -> list[dict[str, int | float]]:
    return [
        {"time": BASE_EPOCH, "open": 1900, "high": 1902, "low": 1899, "close": 1901, "tick_volume": 10, "spread": 15, "real_volume": 0},
        {"time": BASE_EPOCH + 60, "open": 1901, "high": 1903, "low": 1900, "close": 1902, "tick_volume": 12, "spread": 16, "real_volume": 0},
        {"time": BASE_EPOCH + 240, "open": 1902, "high": 1904, "low": 1901, "close": 1903, "tick_volume": 9, "spread": 14, "real_volume": 0},
    ]


def test_valid_dataset_passes_and_reports_gap(tmp_path: Path) -> None:
    report = audit_dataset(make_dataset(tmp_path, valid_rows()))
    assert report["integrity_pass"] is True
    assert report["row_count"] == 3
    assert report["gaps_gt_60s"] == 1
    assert report["gaps_60_to_300_seconds"] == 1


def test_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    root = make_dataset(tmp_path, valid_rows())
    path = root / "XAUUSD_M1_2021_01.csv"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    report = audit_dataset(root)
    assert report["integrity_pass"] is False
    assert any(error.startswith("SHA256_MISMATCH:") for error in report["errors"])


def test_duplicate_timestamp_fails_closed(tmp_path: Path) -> None:
    rows = valid_rows()
    rows[1]["time"] = BASE_EPOCH
    report = audit_dataset(make_dataset(tmp_path, rows))
    assert report["integrity_pass"] is False
    assert report["duplicate_timestamps"] == 1


def test_invalid_ohlc_fails_closed(tmp_path: Path) -> None:
    rows = valid_rows()
    rows[0]["high"] = 1800
    report = audit_dataset(make_dataset(tmp_path, rows))
    assert report["integrity_pass"] is False
    assert report["invalid_ohlc_rows"] == 1
