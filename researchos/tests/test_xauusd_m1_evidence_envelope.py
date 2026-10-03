from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.create_xauusd_m1_evidence_envelope import build_envelope


def _write_chain(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    raw = tmp_path / "XAUUSD_MT5_M1.csv"
    source = tmp_path / "source.json"
    result = tmp_path / "result.json"
    audit = tmp_path / "audit.json"
    raw.write_bytes(b"time,open,high,low,close,tick_volume\n1,1,1,1,1,1\n")
    import hashlib
    raw_sha = hashlib.sha256(raw.read_bytes()).hexdigest()
    source_data = {
        "contract": {
            "asset": "XAUUSD", "timeframe": "M1", "event": "SMA20/100 crossover",
            "label": "hit_threshold_1d", "horizon_days": 1, "threshold_return": 0.0,
            "price_field": "close", "direction_aware": True,
        },
        "dataset": {"sha256": raw_sha},
        "events_data": [],
    }
    source.write_text(json.dumps(source_data), encoding="utf-8")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    result_data = {
        "stage": "M1_WALK_FORWARD_RAW_PROBABILITY",
        "scientific_status": "OOS_RAW_PROBABILITY_ONLY_NO_EDGE_CLAIM",
        "source_artifact": {"sha256": source_sha},
        "dataset": {"sha256": raw_sha},
        "contract": source_data["contract"],
        "split": {
            "train_size": 1, "validation_size": 1, "step_size": 1, "holdout_size": 1,
            "embargo_rule": "training realized_end < validation_start",
            "holdout_rule": "holdout training realized_end < holdout_start",
            "fit_uses_validation_labels": False,
            "fit_uses_holdout_labels": False,
            "validation_windows_overlap": False,
            "holdout_is_disjoint": True,
        },
        "methodology": {
            "forecast_horizon": "1d",
            "feature_availability_timestamp": "event timestamp",
            "selection_policy": "single fixed direction_conditional estimator; no parameter selection",
            "multiple_testing_policy": "not_applicable_single_fixed_estimator",
            "stopping_rule": "none; evaluate the full pre-registered chronological range",
            "replication_rule": "final independent temporal holdout",
            "cost_assumptions": {
                "spread": "not applicable to this probability-only stage",
                "slippage": "not applicable to this probability-only stage",
                "commission": "not applicable to this probability-only stage",
            },
        },
        "holdout": {
            "start": "2025-01-02T00:00:00+00:00",
            "end": "2025-01-02T00:00:00+00:00",
            "holdout_events": 1,
            "pre_holdout_events": 1,
            "training_events": 1,
            "training_end": "2025-01-01T00:00:00+00:00",
            "training_max_realized_end": "2025-01-01T00:30:00+00:00",
            "training_outcome_rate": 1.0,
            "predictions": [{"event_id": "holdout", "timestamp": "2025-01-02T00:00:00+00:00", "probability": 1.0, "label": 1}],
            "model": {"sample_count": 1, "brier_score": 0.0, "log_loss": 0.0, "observed_rate": 1.0},
            "baseline": {"sample_count": 1, "brier_score": 0.0, "log_loss": 0.0, "observed_rate": 1.0},
        },
    }
    result.write_text(json.dumps(result_data), encoding="utf-8")
    result_sha = hashlib.sha256(result.read_bytes()).hexdigest()
    audit.write_text(json.dumps({
        "status": "PASS", "source_sha256": source_sha, "result_artifact_sha256": result_sha,
    }), encoding="utf-8")
    return raw, source, result, audit


def test_valid_chain_builds(tmp_path: Path) -> None:
    paths = _write_chain(tmp_path)
    envelope = build_envelope(*paths, code_commit="03191c86cdff541ac07cfca4291e9801ffab64bc")
    assert envelope["stage"] == "XAUUSD_M1_EVIDENCE_ENVELOPE"
    assert envelope["scientific_status"] == "REPRODUCIBILITY_LINEAGE_ONLY_NO_EDGE_CLAIM"
    assert len(envelope["envelope_sha256"]) == 64
    assert envelope["identity"]["code_commit"] == "03191c86cdff541ac07cfca4291e9801ffab64bc"


@pytest.mark.parametrize("target", ["raw", "source", "result", "audit"])
def test_chain_fails_closed_when_any_artifact_changes(tmp_path: Path, target: str) -> None:
    raw, source, result, audit = _write_chain(tmp_path)
    paths = {"raw": raw, "source": source, "result": result, "audit": audit}
    path = paths[target]
    path.write_bytes(path.read_bytes() + b"tamper")
    with pytest.raises(ValueError):
        build_envelope(raw, source, result, audit, code_commit="03191c86cdff541ac07cfca4291e9801ffab64bc")


def test_dataset_identity_must_bind_to_raw_bytes(tmp_path: Path) -> None:
    raw, source, result, audit = _write_chain(tmp_path)
    source_data = json.loads(source.read_text(encoding="utf-8"))
    source_data["dataset"]["sha256"] = "0" * 64
    source.write_text(json.dumps(source_data), encoding="utf-8")
    with pytest.raises(ValueError, match="raw CSV bytes"):
        build_envelope(raw, source, result, audit, code_commit="03191c86cdff541ac07cfca4291e9801ffab64bc")


def test_holdout_is_mandatory_for_evidence_envelope(tmp_path: Path) -> None:
    raw, source, result, audit = _write_chain(tmp_path)
    result_data = json.loads(result.read_text(encoding="utf-8"))
    del result_data["holdout"]
    result.write_text(json.dumps(result_data), encoding="utf-8")

    audit_data = json.loads(audit.read_text(encoding="utf-8"))
    audit_data["result_artifact_sha256"] = hashlib.sha256(result.read_bytes()).hexdigest()
    audit.write_text(json.dumps(audit_data), encoding="utf-8")

    with pytest.raises(ValueError, match="final holdout artifact is missing"):
        build_envelope(
            raw,
            source,
            result,
            audit,
            code_commit="03191c86cdff541ac07cfca4291e9801ffab64bc",
        )


def test_code_commit_must_be_exact_git_sha(tmp_path: Path) -> None:
    paths = _write_chain(tmp_path)
    with pytest.raises(ValueError, match="exact 40-character Git commit SHA"):
        build_envelope(*paths, code_commit="abc123")
