from __future__ import annotations

from scripts.audit_xauusd_m1_probability_skill import (
    _block_bootstrap_delta,
    _loss,
    _reliability,
    _scores,
)


def test_loss_returns_brier_and_log_loss() -> None:
    brier, log_loss = _loss(0.9, 1)
    assert round(brier, 8) == 0.01
    assert log_loss < 0.11


def test_loss_rejects_invalid_probability() -> None:
    try:
        _loss(float("nan"), 1)
    except ValueError as exc:
        assert "finite" in str(exc)
    else:
        raise AssertionError("non-finite probability must fail closed")


def test_reliability_bins_report_counts_and_observed_rate() -> None:
    rows = [
        {"model_probability": 0.05, "label": 0},
        {"model_probability": 0.15, "label": 1},
        {"model_probability": 1.0, "label": 1},
    ]
    bins = _reliability(rows, "model_probability", bins=10)
    assert sum(item["count"] for item in bins) == 3
    assert bins[0]["count"] == 1
    assert bins[1]["observed_positive_rate"] == 1.0
    assert bins[9]["count"] == 1


def test_block_bootstrap_is_deterministic_and_favors_better_model() -> None:
    rows = []
    for day in range(1, 11):
        rows.extend(
            [
                {
                    "timestamp": f"2025-01-{day:02d}T01:00:00+00:00",
                    "label": 1,
                    "model_probability": 0.9,
                    "baseline_probability": 0.5,
                },
                {
                    "timestamp": f"2025-01-{day:02d}T02:00:00+00:00",
                    "label": 0,
                    "model_probability": 0.1,
                    "baseline_probability": 0.5,
                },
            ]
        )
    first = _block_bootstrap_delta(
        rows, "model_probability", "baseline_probability", 3, seed=42, replicates=100
    )
    second = _block_bootstrap_delta(
        rows, "model_probability", "baseline_probability", 3, seed=42, replicates=100
    )
    assert first == second
    assert first["replicates"] == 100
    assert first["brier_delta_95ci"][1] < 0
    assert first["log_loss_delta_95ci"][1] < 0


def test_score_summary_matches_known_binary_predictions() -> None:
    rows = [
        {"model_probability": 0.9, "label": 1},
        {"model_probability": 0.1, "label": 0},
    ]
    score = _scores(rows, "model_probability")
    assert score["sample_count"] == 2
    assert score["brier_score"] == 0.01
    assert score["observed_rate"] == 0.5
