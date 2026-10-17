"""Evidence-gated meta-metrics for the frozen XAUUSD M1 research run.

This evaluator scores the research process, not whether the market outcome is
profitable. Missing confidence intervals or economic evidence remain explicit.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

METRICS_VERSION = "1.0.0"
_REQUIRED_CONTRACT = {"asset": "XAUUSD", "timeframe": "M1", "label": "hit_threshold_1d"}


def _decode(raw: bytes, name: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{name} artifact is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name} artifact root must be an object")
    return value


def _score_pair(section: dict[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(section, dict):
        raise ValueError(f"{name} must be an object")
    model, baseline = section.get("model"), section.get("baseline")
    if not isinstance(model, dict) or not isinstance(baseline, dict):
        raise ValueError(f"{name} must contain model and baseline score objects")
    result: dict[str, Any] = {}
    for metric in ("brier_score", "log_loss"):
        m, b = model.get(metric), baseline.get(metric)
        if (
            isinstance(m, bool)
            or isinstance(b, bool)
            or not isinstance(m, (int, float))
            or not isinstance(b, (int, float))
        ):
            raise ValueError(f"{name} missing numeric {metric}")
        if (
            not math.isfinite(float(m))
            or not math.isfinite(float(b))
            or m < 0
            or b <= 0
            or (metric == "brier_score" and (m > 1 or b > 1))
        ):
            raise ValueError(f"{name} has invalid {metric}")
        result[metric] = {
            "model": float(m),
            "baseline": float(b),
            "skill_vs_baseline": 1.0 - float(m) / float(b),
            "direction": "lower_is_better",
        }
    result["sample_count"] = model.get("sample_count")
    if (
        isinstance(result["sample_count"], bool)
        or not isinstance(result["sample_count"], int)
        or result["sample_count"] <= 0
    ):
        raise ValueError(f"{name} model sample_count must be a positive integer")
    baseline_count = baseline.get("sample_count")
    if baseline_count is not None and (
        isinstance(baseline_count, bool)
        or not isinstance(baseline_count, int)
        or baseline_count != result["sample_count"]
    ):
        raise ValueError(f"{name} model and baseline sample counts must match")
    return result


def evaluate_xauusd_m1_run(
    real_events_bytes: bytes, walkforward_bytes: bytes, calibration_bytes: bytes
) -> dict[str, Any]:
    """Validate artifact lineage and return fail-closed, interpretable metrics."""
    real = _decode(real_events_bytes, "real-events")
    wf = _decode(walkforward_bytes, "walk-forward")
    cal = _decode(calibration_bytes, "calibration")

    contract = real.get("contract")
    if not isinstance(contract, dict) or any(
        contract.get(k) != v for k, v in _REQUIRED_CONTRACT.items()
    ):
        raise ValueError("real-events artifact does not satisfy the required XAUUSD M1 contract")
    if wf.get("contract") != contract or cal.get("contract") != contract:
        raise ValueError("research artifacts have inconsistent contracts")

    real_sha = hashlib.sha256(real_events_bytes).hexdigest()
    wf_sha = hashlib.sha256(walkforward_bytes).hexdigest()
    cal_source = cal.get("source_artifact")
    wf_source = wf.get("source_artifact")
    cal_result = cal.get("result_artifact")
    if not all(isinstance(item, dict) for item in (cal_source, wf_source, cal_result)):
        raise ValueError("research artifact lineage metadata must be objects")
    if wf_source.get("sha256") != real_sha or cal_source.get("sha256") != real_sha:
        raise ValueError("research artifact lineage does not match the real-events bytes")
    if cal_result.get("sha256") != wf_sha:
        raise ValueError("calibration artifact lineage does not match walk-forward bytes")

    audit = wf.get("audit")
    if not isinstance(audit, dict):
        raise ValueError("walk-forward artifact is missing its audit object")
    required_audits = (
        "holdout_is_disjoint_from_validation",
        "probabilities_in_unit_interval",
        "training_validation_overlap",
        "validation_event_reuse",
        "all_training_labels_realized_before_validation",
        "all_holdout_training_labels_realized_before_holdout",
        "source_sha256_verified_from_bytes",
    )
    missing = [key for key in required_audits if not isinstance(audit.get(key), bool)]
    if missing:
        raise ValueError(f"walk-forward audit fields missing or invalid: {missing}")
    leakage_pass = (
        all(
            audit[key]
            for key in required_audits
            if key not in {"training_validation_overlap", "validation_event_reuse"}
        )
        and not audit["training_validation_overlap"]
        and not audit["validation_event_reuse"]
    )

    aggregate = _score_pair(wf.get("aggregate", {}), "walk-forward aggregate")
    holdout = _score_pair(wf.get("holdout", {}), "final holdout")
    assessment = cal.get("scoring_assessment")
    if not isinstance(assessment, dict):
        raise ValueError("calibration artifact is missing its scoring assessment object")
    calibration_status = assessment.get("status")
    if calibration_status not in {"IMPROVED", "DEGRADED", "NO_CLEAR_IMPROVEMENT"}:
        raise ValueError("calibration artifact has an unknown scoring assessment")

    # Only a complete, finite CI contract counts; arbitrary non-empty metadata is not evidence.
    uncertainty = wf.get("uncertainty")
    intervals = uncertainty.get("confidence_intervals") if isinstance(uncertainty, dict) else None
    has_ci = isinstance(intervals, dict) and all(
        isinstance(intervals.get(split), dict)
        and all(
            isinstance(intervals[split].get(metric), dict)
            and isinstance(intervals[split][metric].get("lower"), (int, float))
            and not isinstance(intervals[split][metric].get("lower"), bool)
            and isinstance(intervals[split][metric].get("upper"), (int, float))
            and not isinstance(intervals[split][metric].get("upper"), bool)
            and math.isfinite(float(intervals[split][metric]["lower"]))
            and math.isfinite(float(intervals[split][metric]["upper"]))
            and 0 <= intervals[split][metric]["lower"] <= intervals[split][metric]["upper"]
            and (metric != "brier_score" or intervals[split][metric]["upper"] <= 1)
            for metric in ("brier_score", "log_loss")
        )
        for split in ("aggregate", "holdout")
    )
    economics_present = isinstance(real.get("economic_audit"), dict) or isinstance(
        wf.get("economic_audit"), dict
    )
    return {
        "metrics_version": METRICS_VERSION,
        "workflow": "FROZEN_XAUUSD_M1",
        "overall_status": "NOT_VALIDATED" if not leakage_pass else "INSUFFICIENT_EVIDENCE",
        "interpretation": "A complete, lineage-checked research run is not proof of predictive edge or profitability.",
        "integrity": {
            "status": "PASS",
            "real_events_sha256": real_sha,
            "walkforward_sha256": wf_sha,
            "calibration_sha256": hashlib.sha256(calibration_bytes).hexdigest(),
        },
        "leakage_controls": {
            "status": "PASS" if leakage_pass else "NOT_VALIDATED",
            "audit": {key: audit[key] for key in required_audits},
        },
        "predictive_skill": {
            "status": "INSUFFICIENT_EVIDENCE" if not has_ci else "REQUIRES_REVIEW",
            "walk_forward": aggregate,
            "final_holdout": holdout,
            "confidence_intervals_available": has_ci,
            "reason": "Point-score improvements alone do not establish statistically reliable improvement; this artifact has no confidence intervals.",
        },
        "calibration": {
            "status": "NOT_VALIDATED" if calibration_status != "IMPROVED" else "PROVISIONAL",
            "source_assessment": calibration_status,
            "brier_delta_calibrated_minus_raw": assessment.get("brier_delta_calibrated_minus_raw"),
            "log_loss_delta_calibrated_minus_raw": assessment.get(
                "log_loss_delta_calibrated_minus_raw"
            ),
            "downstream_use": "BLOCK_CALIBRATED_PROBABILITIES"
            if calibration_status != "IMPROVED"
            else "REQUIRES_SEPARATE_HOLDOUT_REVIEW",
        },
        "economic_edge": {
            "status": "NOT_EVALUATED" if not economics_present else "REQUIRES_INDEPENDENT_AUDIT",
            "reason": "This three-stage run does not itself establish net returns after broker-specific spread, commission, slippage, financing and execution effects.",
        },
        "release_decision": "DO_NOT_CLAIM_TRADING_EDGE",
    }


__all__ = ["METRICS_VERSION", "evaluate_xauusd_m1_run"]
