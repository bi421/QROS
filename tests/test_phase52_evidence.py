from __future__ import annotations

import pytest

from scripts.run_phase52_evidence import _validate_repository_commit


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
