from __future__ import annotations

import hashlib
import json
from pathlib import Path


from scripts.audit_xauusd_m1_oos_calibration import audit
from scripts.run_xauusd_m1_oos_calibration import run


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    events = []
    labels = [True, False] * 6
    for index, label in enumerate(labels):
        events.append(
            {
                "event_id": f"e{index + 1}",
                "timestamp": f"2025-01-01T{index:02d}:00:00+00:00",
                "direction": "bullish",
                "outcome": {
                    "hit_threshold_1d": label,
                    "data_availability": {"realized_end_1d": f"2025-01-01T{index:02d}:30:00+00:00"},
                },
            }
        )
    contract = {
        "asset": "XAUUSD",
        "timeframe": "M1",
        "event": "SMA20/100 crossover",
        "label": "hit_threshold_1d",
        "horizon_days": 1,
        "threshold_return": 0.0,
        "price_field": "close",
        "direction_aware": True,
    }
    source = {"contract": contract, "dataset": {"sha256": "a" * 64}, "events_data": events}
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    predictions = [
        {
            "event_id": f"e{i + 1}",
            "timestamp": f"2025-01-01T{i:02d}:00:00+00:00",
            "direction": "bullish",
            "probability": 0.2 if labels[i] else 0.8,
            "label": int(labels[i]),
        }
        for i in range(12)
    ]
    result = {
        "stage": "M1_WALK_FORWARD_RAW_PROBABILITY",
        "scientific_status": "OOS_RAW_PROBABILITY_ONLY_NO_EDGE_CLAIM",
        "source_artifact": {"sha256": source_sha},
        "contract": contract,
        "dataset": source["dataset"],
        "folds": [{"predictions": predictions}],
    }
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    calibration_path = tmp_path / "calibration.json"
    run(source_path, result_path, calibration_path)
    return source_path, result_path, calibration_path


def test_independent_audit_passes_valid_artifact(tmp_path: Path) -> None:
    source, result, calibration = _fixture(tmp_path)
    report = audit(source, result, calibration)
    assert report["status"] == "PASS"
    assert report["failures"] == []


def test_independent_audit_rejects_tampered_calibration(tmp_path: Path) -> None:
    source, result, calibration = _fixture(tmp_path)
    data = json.loads(calibration.read_text(encoding="utf-8"))
    data["predictions"][0]["calibrated_probability"] = 0.123456
    calibration.write_text(json.dumps(data), encoding="utf-8")
    report = audit(source, result, calibration)
    assert report["status"] == "FAIL"
    assert any("independent reconstruction" in failure for failure in report["failures"])


def test_independent_audit_rejects_result_sha_tampering(tmp_path: Path) -> None:
    source, result, calibration = _fixture(tmp_path)
    data = json.loads(result.read_text(encoding="utf-8"))
    data["folds"][0]["predictions"][11]["probability"] = 0.99
    result.write_text(json.dumps(data), encoding="utf-8")
    report = audit(source, result, calibration)
    assert report["status"] == "FAIL"
    assert "result SHA mismatch" in report["failures"]


def test_independent_audit_rejects_result_source_binding_tampering(tmp_path: Path) -> None:
    source, result, calibration = _fixture(tmp_path)
    data = json.loads(result.read_text(encoding="utf-8"))
    data["source_artifact"]["sha256"] = "b" * 64
    result.write_text(json.dumps(data), encoding="utf-8")
    report = audit(source, result, calibration)
    assert report["status"] == "FAIL"
    assert "result SHA mismatch" in report["failures"]
    assert "result source SHA mismatch" in report["failures"]
