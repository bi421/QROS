from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.run_xauusd_m1_oos_calibration import _pava, run


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
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
    source = {
        "contract": {
            "asset": "XAUUSD",
            "timeframe": "M1",
            "event": "SMA20/100 crossover",
            "label": "hit_threshold_1d",
            "horizon_days": 1,
            "threshold_return": 0.0,
            "price_field": "close",
            "direction_aware": True,
        },
        "dataset": {"sha256": "a" * 64},
        "events_data": events,
    }
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps(source, separators=(",", ":")), encoding="utf-8")
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    predictions = []
    for index, label in enumerate(labels):
        predictions.append(
            {
                "event_id": f"e{index + 1}",
                "timestamp": f"2025-01-01T{index:02d}:00:00+00:00",
                "direction": "bullish",
                "probability": 0.2 if label else 0.8,
                "label": int(label),
            }
        )
    result = {
        "stage": "M1_WALK_FORWARD_RAW_PROBABILITY",
        "scientific_status": "OOS_RAW_PROBABILITY_ONLY_NO_EDGE_CLAIM",
        "source_artifact": {"sha256": source_sha},
        "contract": source["contract"],
        "dataset": source["dataset"],
        "folds": [{"predictions": predictions}],
    }
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    return source_path, result_path


def test_pava_returns_monotone_block_rates() -> None:
    breakpoints = _pava([(0.1, 1), (0.2, 0), (0.3, 0), (0.4, 1)])
    values = [value for _, value in breakpoints]
    assert values == sorted(values)
    assert all(0.0 <= value <= 1.0 for value in values)


def test_pava_aggregates_duplicate_probabilities() -> None:
    breakpoints = _pava([(0.5, 0), (0.5, 1), (0.5, 1), (0.6, 1)])
    assert breakpoints[0] == (0.5, round(2 / 3, 12))
    assert all(x != 0.5 for x, _ in breakpoints[1:])


def test_oos_calibration_uses_prior_realized_outcomes_only(tmp_path: Path) -> None:
    source, result = _fixture(tmp_path)
    output = run(source, result, tmp_path / "calibrated.json")
    assert output["scientific_status"] == "OOS_CALIBRATION_ONLY_NO_EDGE_CLAIM"
    assert len(output["predictions"]) == 2
    assert output["calibration"]["warmup_excluded_predictions"] == 10
    assert output["calibration"]["eligible_oos_predictions"] == 2
    assert output["raw_score"]["sample_count"] == output["calibrated_score"]["sample_count"] == 2
    assert output["calibration"]["refit_count"] == 1
    assert len(output["calibration"]["fit_summaries"]) == 1
    assert output["calibration"]["fit_summaries"][0]["training_event_count"] == 10
    assert output["predictions"][0]["calibration_fit_id"] == 1
    assert output["predictions"][0]["calibration_training_event_count"] == 10
    assert output["predictions"][1]["calibration_fit_id"] == 1
    assert output["predictions"][1]["calibration_training_event_count"] == 11
    assert "calibration_training_event_ids" not in output["predictions"][0]


def test_oos_calibration_fails_without_both_prior_classes(tmp_path: Path) -> None:
    source, result = _fixture(tmp_path)
    source_data = json.loads(source.read_text(encoding="utf-8"))
    result_data = json.loads(result.read_text(encoding="utf-8"))
    for event in source_data["events_data"][:11]:
        event["outcome"]["hit_threshold_1d"] = True
    for prediction in result_data["folds"][0]["predictions"][:11]:
        prediction["label"] = 1
    source.write_text(json.dumps(source_data), encoding="utf-8")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    result_data["source_artifact"]["sha256"] = source_sha
    result.write_text(json.dumps(result_data), encoding="utf-8")
    with pytest.raises(ValueError, match="No OOS predictions"):
        run(source, result, tmp_path / "calibrated.json")
