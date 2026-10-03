from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.audit_phase52_evidence import (
    _baseline_brier,
    _configuration_hash,
    _model_brier,
    audit,
)

from researchos.experiments.phase51.statistics import (
    confidence_interval_diff,
    evaluate_significance,
)


def _payload() -> dict[str, object]:
    configuration = {
        "symbol": "XAUUSD",
        "timeframe": "1d",
        "horizon": 5,
        "threshold": 0.0,
        "train_size": 10,
        "validation_size": 5,
        "step_size": 5,
        "holdout_size": 40,
        "neighbors": 25,
        "spread": "fixed:0.0",
        "slippage": "fixed:0.0",
        "commission": "fixed:0.0",
    }
    predictions = []
    base_timestamp = datetime(2025, 1, 20, tzinfo=timezone.utc)
    for i in range(40):
        label = 1 if i % 2 == 0 else -1
        timestamp = base_timestamp + timedelta(days=i)
        realized_end = timestamp + timedelta(days=5)
        predictions.append(
            {
                "timestamp": timestamp.isoformat(),
                "realized_end": realized_end.isoformat(),
                "prediction": label,
                "probabilities": {
                    "-1": 0.10 if label == 1 else 0.85,
                    "0": 0.05,
                    "1": 0.85 if label == 1 else 0.10,
                },
                "label": label,
            }
        )

    model_brier = _model_brier(predictions)
    baseline_brier = _baseline_brier(predictions, 1)
    significance = evaluate_significance(
        [int(row["prediction"]) for row in predictions],
        [1] * len(predictions),
        [int(row["label"]) for row in predictions],
    ).to_dict()
    accuracy_delta_ci_95 = confidence_interval_diff(
        [float(int(row["prediction"]) == int(row["label"])) for row in predictions],
        [float(1 == int(row["label"])) for row in predictions],
    )
    return {
        "schema": "researchos/phase52/evidence/v3",
        "repository_commit": "03191c86cdff541a03545ff521c667e4ccd733c9",
        "configuration": configuration,
        "configuration_hash": _configuration_hash(configuration),
        "feature_set_scope": [
            "PRICE_ONLY",
            "PRICE + DXY",
            "PRICE + US10Y",
            "PRICE + VIX",
            "PRICE + ALL",
        ],
        "sources": {source: {"sha256": "0" * 64} for source in ("XAUUSD", "DXY", "US10Y", "VIX")},
        "common_sample": {
            "count": 60,
            "first": "2025-01-01",
            "last": "2025-04-01",
            "timestamps_sha256": "0" * 64,
        },
        "holdout_contract": {
            "holdout_size": 40,
            "wfo_aggregate_excludes_holdout": True,
            "selection_excludes_holdout": True,
            "calibration_excludes_holdout": True,
        },
        "results": {
            feature_set: {
                "metadata": {
                    "feature_set": feature_set,
                    "feature_set_search_scope": [
                        "PRICE_ONLY",
                        "PRICE + DXY",
                        "PRICE + US10Y",
                        "PRICE + VIX",
                        "PRICE + ALL",
                    ],
                    "holdout_used_for_feature_selection": False,
                    "temporal_contract": {
                        "feature_availability_convention": "observation_timestamp_after_source_bar_close",
                        "label_definition": "close[t+5] / close[t] - 1",
                        "walk_forward_training_rule": "realized_end < validation_start",
                        "final_holdout_training_rule": "realized_end < holdout_start",
                        "holdout_is_chronologically_disjoint": True,
                        "holdout_excluded_from_wfo_aggregate": True,
                    },
                    "calibration_contract": {
                        "parameter_fitting_performed": False,
                        "holdout_excluded": True,
                        "training_population": "walk-forward validation predictions only",
                    },
                    "wfo_folds": [
                        {
                            "fold": 1,
                            "training_start": "2025-01-01T00:00:00+00:00",
                            "training_end": "2025-01-09T00:00:00+00:00",
                            "training_sample_count": 10,
                            "training_max_realized_end": "2025-01-06T00:00:00+00:00",
                            "validation_start": "2025-01-10T00:00:00+00:00",
                            "validation_end": "2025-01-14T00:00:00+00:00",
                            "validation_realized_end": "2025-01-19T00:00:00+00:00",
                            "validation_sample_count": 5,
                        }
                    ],
                    "holdout": {
                        "start": "2025-01-20T00:00:00+00:00",
                        "end": "2025-02-28T00:00:00+00:00",
                        "terminal_realized_end": "2025-03-05T00:00:00+00:00",
                        "holdout_events": 40,
                        "training_events": 15,
                        "training_start": "2025-01-01T00:00:00+00:00",
                        "training_end": "2025-01-15T00:00:00+00:00",
                        "training_max_realized_end": "2025-01-19T00:00:00+00:00",
                        "fit_is_pre_holdout_only": True,
                        "selection_frozen_before_scoring": True,
                        "holdout_used_for_selection": False,
                        "prediction_count": 40,
                        "predictions": predictions,
                        "baseline_prediction": 1,
                        "model": {
                            "sample_count": 40,
                            "accuracy": 1.0,
                            "brier_score": model_brier,
                        },
                        "baseline": {
                            "sample_count": 40,
                            "accuracy": 0.5,
                            "brier_score": baseline_brier,
                        },
                        "significance": significance,
                        "accuracy_delta_ci_95": {
                            "lower": accuracy_delta_ci_95[0],
                            "upper": accuracy_delta_ci_95[1],
                        },
                    },
                }
            }
            for feature_set in (
                "PRICE_ONLY",
                "PRICE + DXY",
                "PRICE + US10Y",
                "PRICE + VIX",
                "PRICE + ALL",
            )
        },
    }


def test_phase52_evidence_auditor_recomputes_holdout_metrics(tmp_path: Path) -> None:
    path = tmp_path / "phase52_evidence.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")

    result = audit(path)

    assert result["status"] == "PASS"
    assert result["checked_feature_sets"] == 5


def test_phase52_evidence_auditor_detects_holdout_score_tampering(tmp_path: Path) -> None:
    payload = _payload()
    payload["results"]["PRICE_ONLY"]["metadata"]["holdout"]["model"]["brier_score"] += 0.01
    path = tmp_path / "phase52_evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = audit(path)

    assert result["status"] == "FAIL"
    assert "PRICE_ONLY: holdout model Brier does not recompute" in result["failures"]


def _blocked_payload() -> dict[str, object]:
    configuration = {
        "symbol": "XAUUSD",
        "timeframe": "1d",
        "horizon": 5,
        "threshold": 0.0,
        "train_size": 1000,
        "validation_size": 200,
        "step_size": 200,
        "holdout_size": 40,
        "neighbors": 25,
        "spread": "fixed:0.0",
        "slippage": "fixed:0.0",
        "commission": "fixed:0.0",
    }
    feature_sets = ["PRICE_ONLY", "PRICE + DXY", "PRICE + US10Y", "PRICE + VIX", "PRICE + ALL"]
    results = {
        feature_set: {
            "outcome": "BLOCKED",
            "metadata": {
                "feature_set": feature_set,
                "blocked_reason": "insufficient prepared observations",
                "holdout_predictions_present": False,
                "holdout_metrics_present": False,
            },
        }
        for feature_set in feature_sets
    }
    return {
        "schema": "researchos/phase52/evidence/v3",
        "repository_commit": "a07dad913e06b1eff812ce1bd4efd550db43e5c6",
        "execution_status": "BLOCKED",
        "blocking": {
            "stage": "prepared_execution_gate",
            "reason": "insufficient prepared observations",
            "holdout_scoring_executed": False,
        },
        "configuration": configuration,
        "configuration_hash": _configuration_hash(configuration),
        "sample_requirements": {
            "required_prepared_samples": 1245,
            "actual_prepared_samples": 1181,
            "common_observations": 1246,
        },
        "feature_set_scope": feature_sets,
        "sources": {
            source: {"sha256": "0" * 64, "identity": identity}
            for source, identity in {
                "XAUUSD": "XAUUSD 2021-2025 research series",
                "DXY": "Dukascopy dollaridxusd; secondary DXY series",
                "US10Y": "FRED DGS10",
                "VIX": "FRED VIXCLS",
            }.items()
        },
        "common_sample": {
            "count": 1246,
            "first": "2021-01-04",
            "last": "2025-12-30",
            "dropped_from_xauusd": 1,
            "timestamps_sha256": "0" * 64,
        },
        "holdout_contract": {
            "holdout_size": 40,
            "wfo_aggregate_excludes_holdout": True,
            "selection_excludes_holdout": True,
            "calibration_excludes_holdout": True,
            "predictions_present": False,
            "metrics_present": False,
        },
        "results": results,
        "reproducibility_hashes": {},
        "dxy_provenance": {
            "provider": "Dukascopy",
            "instrument": "dollaridxusd",
            "source_type": "secondary",
            "ice_dxy_equivalence": "NOT PROVEN",
        },
    }


def test_phase52_blocked_evidence_audits_pass(tmp_path: Path) -> None:
    path = tmp_path / "blocked.json"
    path.write_text(json.dumps(_blocked_payload()), encoding="utf-8")
    result = audit(path)
    assert result["status"] == "PASS"
    assert result["execution_status"] == "BLOCKED"
    assert result["scientific_status"] == "BLOCKED"


def test_phase52_blocked_evidence_rejects_tampering(tmp_path: Path) -> None:
    mutations = {
        "fabricated holdout predictions": lambda p: p["results"]["PRICE_ONLY"]["metadata"].update(
            {"holdout": {"predictions": [{"prediction": 1}]}}
        ),
        "fabricated numerical metrics": lambda p: p["results"]["PRICE_ONLY"].update(
            {"model": {"accuracy": 1.0}}
        ),
        "invalid repository SHA": lambda p: p.update({"repository_commit": "bad"}),
        "inconsistent sample counts": lambda p: p["sample_requirements"].update(
            {"actual_prepared_samples": 1245}
        ),
        "modified feature-set scope": lambda p: p.update({"feature_set_scope": ["PRICE_ONLY"]}),
        "invalid source SHA-256": lambda p: p["sources"]["DXY"].update({"sha256": "not-a-sha"}),
        "missing blocking reason": lambda p: p["blocking"].update({"reason": ""}),
    }
    for label, mutate in mutations.items():
        payload = _blocked_payload()
        mutate(payload)
        path = tmp_path / f"{label.replace(' ', '_')}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        result = audit(path)
        assert result["status"] == "FAIL", label
