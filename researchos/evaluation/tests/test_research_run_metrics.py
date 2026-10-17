from __future__ import annotations

import hashlib
import json
import math

from researchos.evaluation.research_run_metrics import evaluate_xauusd_m1_run


def _artifact(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _fixtures():
    contract = {"asset": "XAUUSD", "timeframe": "M1", "label": "hit_threshold_1d"}
    real = _artifact({"stage": "M1_REAL_EVENTS", "contract": contract})
    wf_value = {
        "stage": "M1_WALK_FORWARD_RAW_PROBABILITY",
        "contract": contract,
        "source_artifact": {"sha256": hashlib.sha256(real).hexdigest()},
        "aggregate": {
            "model": {"sample_count": 100, "brier_score": 0.24, "log_loss": 0.68},
            "baseline": {"sample_count": 100, "brier_score": 0.25, "log_loss": 0.69},
        },
        "holdout": {
            "model": {"sample_count": 50, "brier_score": 0.245, "log_loss": 0.685},
            "baseline": {"sample_count": 50, "brier_score": 0.25, "log_loss": 0.69},
        },
        "audit": {
            "holdout_is_disjoint_from_validation": True,
            "probabilities_in_unit_interval": True,
            "training_validation_overlap": False,
            "validation_event_reuse": False,
            "all_training_labels_realized_before_validation": True,
            "all_holdout_training_labels_realized_before_holdout": True,
            "source_sha256_verified_from_bytes": True,
        },
    }
    wf = _artifact(wf_value)
    cal = _artifact(
        {
            "contract": contract,
            "source_artifact": {"sha256": hashlib.sha256(real).hexdigest()},
            "result_artifact": {"sha256": hashlib.sha256(wf).hexdigest()},
            "scoring_assessment": {
                "status": "DEGRADED",
                "brier_delta_calibrated_minus_raw": 0.01,
                "log_loss_delta_calibrated_minus_raw": 0.02,
            },
        }
    )
    return real, wf, cal


def test_metrics_report_skill_but_do_not_overclaim_edge() -> None:
    result = evaluate_xauusd_m1_run(*_fixtures())
    assert result["integrity"]["status"] == "PASS"
    assert result["leakage_controls"]["status"] == "PASS"
    assert math.isclose(
        result["predictive_skill"]["walk_forward"]["brier_score"]["skill_vs_baseline"], 0.04
    )
    assert result["predictive_skill"]["confidence_intervals_available"] is False
    assert result["overall_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["calibration"]["status"] == "NOT_VALIDATED"
    assert result["calibration"]["downstream_use"] == "BLOCK_CALIBRATED_PROBABILITIES"
    assert result["economic_edge"]["status"] == "NOT_EVALUATED"
    assert result["release_decision"] == "DO_NOT_CLAIM_TRADING_EDGE"


def test_metrics_fail_closed_on_artifact_lineage_mismatch() -> None:
    real, wf, cal = _fixtures()
    try:
        evaluate_xauusd_m1_run(real, wf + b" ", cal)
    except ValueError as exc:
        assert "lineage" in str(exc)
    else:
        raise AssertionError("lineage mismatch was not rejected")


def test_metrics_fail_closed_on_missing_audit_field() -> None:
    real, wf, cal = _fixtures()
    wf_value = json.loads(wf)
    del wf_value["audit"]["validation_event_reuse"]
    wf_bad = _artifact(wf_value)
    cal_value = json.loads(cal)
    cal_value["result_artifact"]["sha256"] = hashlib.sha256(wf_bad).hexdigest()
    try:
        evaluate_xauusd_m1_run(real, wf_bad, _artifact(cal_value))
    except ValueError as exc:
        assert "audit fields" in str(exc)
    else:
        raise AssertionError("missing audit field was not rejected")


def test_metrics_mark_leakage_failure_not_validated() -> None:
    real, wf, cal = _fixtures()
    wf_value = json.loads(wf)
    wf_value["audit"]["training_validation_overlap"] = True
    wf_bad = _artifact(wf_value)
    cal_value = json.loads(cal)
    cal_value["result_artifact"]["sha256"] = hashlib.sha256(wf_bad).hexdigest()
    result = evaluate_xauusd_m1_run(real, wf_bad, _artifact(cal_value))
    assert result["leakage_controls"]["status"] == "NOT_VALIDATED"
    assert result["overall_status"] == "NOT_VALIDATED"


def test_metrics_rejects_malformed_lineage_metadata() -> None:
    real, wf, cal = _fixtures()
    wf_value = json.loads(wf)
    wf_value["source_artifact"] = []
    wf_bad = _artifact(wf_value)
    cal_value = json.loads(cal)
    cal_value["result_artifact"]["sha256"] = hashlib.sha256(wf_bad).hexdigest()
    try:
        evaluate_xauusd_m1_run(real, wf_bad, _artifact(cal_value))
    except ValueError as exc:
        assert "lineage metadata" in str(exc)
    else:
        raise AssertionError("malformed lineage metadata was not rejected")


def test_metrics_rejects_boolean_scores_and_mismatched_sample_counts() -> None:
    real, wf, cal = _fixtures()
    wf_value = json.loads(wf)
    wf_value["aggregate"]["model"]["brier_score"] = True
    wf_bad = _artifact(wf_value)
    cal_value = json.loads(cal)
    cal_value["result_artifact"]["sha256"] = hashlib.sha256(wf_bad).hexdigest()
    try:
        evaluate_xauusd_m1_run(real, wf_bad, _artifact(cal_value))
    except ValueError as exc:
        assert "numeric brier_score" in str(exc)
    else:
        raise AssertionError("boolean score was accepted as numeric")

    wf_value = json.loads(wf)
    wf_value["aggregate"]["baseline"]["sample_count"] = 99
    wf_bad = _artifact(wf_value)
    cal_value = json.loads(cal)
    cal_value["result_artifact"]["sha256"] = hashlib.sha256(wf_bad).hexdigest()
    try:
        evaluate_xauusd_m1_run(real, wf_bad, _artifact(cal_value))
    except ValueError as exc:
        assert "sample counts must match" in str(exc)
    else:
        raise AssertionError("mismatched sample counts were accepted")
