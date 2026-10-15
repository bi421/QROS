from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts.audit_xauusd_m1_edge_costs import audit


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    data_path = tmp_path / "xauusd.csv"
    rows = [
        ("2025-01-01T00:00:00+00:00", 100.0, 100.0, 5),
        ("2025-01-01T00:01:00+00:00", 100.0, 100.0, 5),
        ("2025-01-01T01:00:00+00:00", 102.0, 102.0, 6),
        ("2025-01-01T02:00:00+00:00", 102.0, 102.0, 5),
        ("2025-01-01T02:01:00+00:00", 102.0, 102.0, 5),
        ("2025-01-01T03:00:00+00:00", 101.0, 101.0, 7),
    ]
    with data_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time", "open", "close", "spread"])
        writer.writerows(rows)

    source_path = tmp_path / "events.json"
    events = [
        {
            "event_id": "e1_bullish",
            "timestamp": rows[0][0],
            "event_price": 100.0,
            "outcome": {
                "return_1d": 0.02,
                "hit_threshold_1d": True,
                "data_availability": {"realized_end_1d": rows[2][0]},
            },
        },
        {
            "event_id": "e2_bearish",
            "timestamp": rows[3][0],
            "event_price": 102.0,
            "outcome": {
                "return_1d": (101.0 / 102.0) - 1.0,
                "hit_threshold_1d": True,
                "data_availability": {"realized_end_1d": rows[5][0]},
            },
        },
    ]
    source = {
        "contract": {"asset": "XAUUSD", "timeframe": "M1", "label": "hit_threshold_1d"},
        "dataset": {"sha256": hashlib.sha256(data_path.read_bytes()).hexdigest()},
        "events_data": events,
    }
    source_path.write_text(json.dumps(source), encoding="utf-8")
    return source_path, data_path


def test_cost_audit_uses_verified_dataset_and_reports_slippage_stress(tmp_path: Path) -> None:
    source, data = _fixture(tmp_path)
    report = audit(source, data)

    assert report["status"] == "COMPUTED_RESEARCH_DIAGNOSTIC_NOT_EDGE_CERTIFICATION"
    assert report["dataset"]["identity_verified"] is True
    assert report["counts"]["events_with_entry_and_exit_bars"] == 2
    assert report["counts"]["non_overlapping_events"] == 2
    scenarios = report["scenarios"]
    assert [row["slippage_points_per_side"] for row in scenarios] == [0, 1, 2, 5, 10]
    assert (
        scenarios[0]["full_history_overlapping_event_diagnostic"]["signal_direction"][
            "compounded_return_pct"
        ]
        is None
    )
    no_slippage = scenarios[0]["full_history_non_overlapping_1d_diagnostic"]["signal_direction"][
        "mean_return_pct"
    ]
    ten_points = scenarios[-1]["full_history_non_overlapping_1d_diagnostic"]["signal_direction"][
        "mean_return_pct"
    ]
    assert ten_points < no_slippage


def test_cost_audit_binds_final_holdout_to_walkforward_artifact(tmp_path: Path) -> None:
    source, data = _fixture(tmp_path)
    walkforward = tmp_path / "walkforward.json"
    walkforward.write_text(
        json.dumps(
            {
                "stage": "M1_WALK_FORWARD_RAW_PROBABILITY",
                "source_artifact": {"sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
                "holdout": {"predictions": [{"event_id": "e1_bullish"}]},
            }
        ),
        encoding="utf-8",
    )

    report = audit(source, data, walkforward)

    assert report["walkforward_holdout"]["holdout_prediction_count"] == 1
    assert report["walkforward_holdout"]["holdout_events_with_cost_inputs"] == 1
    assert report["walkforward_holdout"]["holdout_non_overlapping_events"] == 1
    assert (
        report["scenarios"][0]["final_holdout_non_overlapping_1d_diagnostic"]["signal_direction"][
            "trade_count"
        ]
        == 1
    )


def test_cost_audit_fails_closed_on_dataset_hash_mismatch(tmp_path: Path) -> None:
    source, data = _fixture(tmp_path)
    data.write_text(data.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Dataset SHA-256 mismatch"):
        audit(source, data)


def test_cost_audit_fails_closed_on_source_return_mismatch(tmp_path: Path) -> None:
    source, data = _fixture(tmp_path)
    source_data = json.loads(source.read_text(encoding="utf-8"))
    source_data["events_data"][0]["outcome"]["return_1d"] = 0.03
    source.write_text(json.dumps(source_data), encoding="utf-8")

    with pytest.raises(ValueError, match="return_1d does not recompute"):
        audit(source, data)


def test_cost_audit_excludes_entries_after_long_market_gap(tmp_path: Path) -> None:
    source, data = _fixture(tmp_path)
    rows = list(csv.DictReader(data.open(encoding="utf-8")))
    rows[1]["time"] = "2025-01-01T00:10:00+00:00"
    with data.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["time", "open", "close", "spread"])
        writer.writeheader()
        writer.writerows(rows)
    source_data = json.loads(source.read_text(encoding="utf-8"))
    source_data["dataset"]["sha256"] = hashlib.sha256(data.read_bytes()).hexdigest()
    source.write_text(json.dumps(source_data), encoding="utf-8")

    report = audit(source, data)

    assert report["counts"]["skipped"]["entry_gap_over_5m"] >= 1
