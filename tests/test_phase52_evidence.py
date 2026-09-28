from __future__ import annotations

import pytest

from scripts.run_phase52_evidence import (
    FEATURE_SET_NAMES,
    _build_blocked_payload,
    _validate_holdout_results,
    _validate_repository_commit,
)


def test_repository_commit_requires_exact_40_character_git_sha() -> None:
    assert _validate_repository_commit(
        "03191c86cdff541a03545ff521c667e4ccd733c9a"
    ) == "03191c86cdff541a03545ff521c667e4ccd733c9a"


@pytest.mark.parametrize(
    "value",
    [
        "unknown",
        "abc123",
        "0" * 39,
        "0" * 41,
        "g" * 40,
    ],
)
def test_repository_commit_rejects_non_exact_sha(value: str) -> None:
    with pytest.raises(ValueError, match="exact 40-character Git SHA"):
        _validate_repository_commit(value)


def _valid_holdout_results(holdout_size: int = 40) -> dict[str, object]:
    return {
        feature_set: {
            "metadata": {
                "feature_set": feature_set,
                "holdout": {
                    "holdout_events": holdout_size,
                    "prediction_count": holdout_size,
                    "predictions": [{} for _ in range(holdout_size)],
                    "holdout_used_for_selection": False,
                    "fit_is_pre_holdout_only": True,
                },
                "temporal_contract": {
                    "holdout_excluded_from_wfo_aggregate": True,
                },
                "calibration_contract": {
                    "holdout_excluded": True,
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
    }


def test_evidence_generation_requires_a_positive_holdout_contract() -> None:
    with pytest.raises(ValueError, match="holdout event count"):
        _validate_holdout_results(_valid_holdout_results(39), holdout_size=40)


def test_evidence_report_preserves_holdout_scope_and_lineage() -> None:
    payload = {
        "repository_commit": "03191c86cdff541a03545ff521c667e4ccd733c9a",
        "common_sample": {"count": 1246, "first": "2021-01-04", "last": "2025-12-30"},
        "sources": {"DXY": {"identity": "Dukascopy dollaridxusd; secondary DXY series"}},
        "results": {
            name: {
                "outcome": "UNCERTAIN",
                "model": {"sample_count": 1200, "accuracy": 0.5, "brier_score": 0.2},
                "cost": {"net_accuracy_all": 0.5},
                "significance": {"p_value": 1.0, "significant": False},
                "metadata": {
                    "holdout": {
                        "holdout_events": 40,
                        "start": "2025-01-01T00:00:00+00:00",
                        "end": "2025-03-01T00:00:00+00:00",
                        "model": {"sample_count": 40, "accuracy": 0.5, "brier_score": 0.2},
                        "significance": {"p_value": 1.0},
                        "accuracy_delta_ci_95": {"lower": -0.1, "upper": 0.1},
                    }
                },
            }
            for name in (
                "PRICE_ONLY",
                "PRICE + DXY",
                "PRICE + US10Y",
                "PRICE + VIX",
                "PRICE + ALL",
            )
        },
        "reproducibility_hashes": {},
    }
    output = __import__("pathlib").Path("phase52_evidence_test.md")
    try:
        from scripts.run_phase52_evidence import _write_report

        _write_report(output, payload)
        report = output.read_text(encoding="utf-8")
        assert "Final independent holdout" in report
        assert "Holdout n" in report
        assert "2025-01-01T00:00:00+00:00" in report
    finally:
        if output.exists():
            output.unlink()


def test_blocked_evidence_payload_is_truthful(tmp_path) -> None:
    paths = {}
    counts = {}
    for name in ("XAUUSD", "DXY", "US10Y", "VIX"):
        path = tmp_path / f"{name}.csv"
        path.write_text(f"{name},2025-01-01,1\n", encoding="utf-8")
        paths[name] = path
        counts[name] = 1
    configuration = {
        "symbol": "XAUUSD", "timeframe": "1d", "horizon": 5, "threshold": 0.0,
        "train_size": 1000, "validation_size": 200, "step_size": 200, "holdout_size": 40,
        "neighbors": 25, "spread": "fixed:0.0", "slippage": "fixed:0.0", "commission": "fixed:0.0",
    }
    reason = "insufficient prepared observations"
    results = {
        name: {
            "outcome": "BLOCKED",
            "metadata": {
                "feature_set": name,
                "blocked_reason": reason,
                "holdout_predictions_present": False,
                "holdout_metrics_present": False,
            },
        }
        for name in FEATURE_SET_NAMES
    }
    payload = _build_blocked_payload(
        repository_commit="a07dad913e06b1eff812ce1bd4efd550db43e5c6",
        configuration=configuration,
        paths=paths,
        original_counts=counts,
        common_ts=["2025-01-01T00:00:00+00:00"],
        results=results,
        blocking_stage="prepared_execution_gate",
        blocking_reason=reason,
        actual_prepared_samples=1181,
    )
    assert payload["execution_status"] == "BLOCKED"
    assert payload["repository_commit"] == "a07dad913e06b1eff812ce1bd4efd550db43e5c6"
    assert payload["sample_requirements"]["required_prepared_samples"] == 1245
    assert payload["sample_requirements"]["actual_prepared_samples"] == 1181
    assert payload["holdout_contract"]["predictions_present"] is False
    assert payload["holdout_contract"]["metrics_present"] is False
    assert all(result["outcome"] == "BLOCKED" for result in payload["results"].values())
    assert all("holdout" not in result["metadata"] for result in payload["results"].values())
