from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_phase52_evidence import audit, _configuration_hash, _model_brier, _baseline_brier


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
    for i in range(40):
        label = 1 if i % 2 == 0 else -1
        timestamp_day = i + 10
        predictions.append(
            {
                "timestamp": f"2025-02-{timestamp_day:02d}T00:00:00+00:00",
                "realized_end": f"2025-03-{i + 1:02d}T00:00:00+00:00",
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
    return {
        "schema": "researchos/phase52/evidence/v3",
        "repository_commit": "03191c86cdff541a03545ff521c667e4ccd733c9a",
        "configuration": configuration,
        "configuration_hash": _configuration_hash(configuration),
        "feature_set_scope": [
            "PRICE_ONLY",
            "PRICE + DXY",
            "PRICE + US10Y",
            "PRICE + VIX",
            "PRICE + ALL",
        ],
        "sources": {
            source: {"sha256": "0" * 64}
            for source in ("XAUUSD", "DXY", "US10Y", "VIX")
        },
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
                        "accuracy_delta_ci_95": {
                            "lower": 0.1,
                            "upper": 0.9,
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
