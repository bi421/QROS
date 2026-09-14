from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone


from scripts.audit_xauusd_m1_walkforward import audit
from scripts.run_xauusd_m1_walkforward import run


def _artifact(tmp_path):
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    events = []
    for i in range(30):
        ts = base + timedelta(days=i)
        events.append(
            {
                "event_id": f"e{i}",
                "timestamp": ts.isoformat(),
                "direction": "bullish" if i % 2 == 0 else "bearish",
                "outcome": {
                    "hit_threshold_1d": i % 3 != 0,
                    "data_availability": {"realized_end_1d": (ts + timedelta(hours=1)).isoformat()},
                },
            }
        )
    path = tmp_path / "events.json"
    path.write_text(
        json.dumps(
            {
                "contract": {"asset": "XAUUSD", "timeframe": "M1", "label": "hit_threshold_1d"},
                "dataset": {"sha256": "dataset"},
                "events_data": events,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_independent_auditor_passes_valid_artifact(tmp_path):
    source = _artifact(tmp_path)
    output = tmp_path / "walkforward.json"
    run(source, output, train_size=10, validation_size=5, step_size=5)
    result = audit(output)
    assert result["status"] == "PASS"
    assert result["prediction_records"] == 20
    assert all(result["checks"].values())


def test_independent_auditor_detects_score_tampering(tmp_path):
    source = _artifact(tmp_path)
    output = tmp_path / "walkforward.json"
    run(source, output, train_size=10, validation_size=5, step_size=5)
    report = json.loads(output.read_text(encoding="utf-8"))
    report["aggregate"]["model"]["brier_score"] += 0.01
    output.write_text(json.dumps(report), encoding="utf-8")
    result = audit(output)
    assert result["status"] == "FAIL"
    assert any("aggregate model score does not recompute" in item for item in result["failures"])


def test_independent_auditor_detects_validation_reuse(tmp_path):
    source = _artifact(tmp_path)
    output = tmp_path / "walkforward.json"
    run(source, output, train_size=10, validation_size=5, step_size=5)
    report = json.loads(output.read_text(encoding="utf-8"))
    report["folds"][1]["predictions"][0] = report["folds"][0]["predictions"][0]
    output.write_text(json.dumps(report), encoding="utf-8")
    result = audit(output)
    assert result["status"] == "FAIL"
    assert any("validation event reused" in item for item in result["failures"])
