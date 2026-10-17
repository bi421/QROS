import pytest

from researchos.orchestration.logistic_probability import fit_evaluate_logistic


def _rows(start, stop):
    rows = []
    for i in range(start, stop):
        z = (i % 11) / 5.0
        body = (i % 7) / 7.0
        upper = (i % 5) / 5.0
        lower = ((i + 2) % 5) / 5.0
        aligned = float(i % 2)
        label = int(z + aligned * 0.7 + body * 0.2 > 1.25)
        rows.append(
            {
                "z_speed": z,
                "body_ratio": body,
                "upper_wick_ratio": upper,
                "lower_wick_ratio": lower,
                "h1_aligned": aligned,
                "label": label,
            }
        )
    return rows


def test_logistic_fits_train_and_reports_holdout_vs_prevalence_baseline():
    result = fit_evaluate_logistic(_rows(0, 200), _rows(300, 380))
    assert result["status"] == "FITTED_TRAIN_EVALUATED_HOLDOUT"
    assert result["train_n"] == 200
    assert result["holdout_n"] == 80
    assert set(result["standardized_coefficients"]) == {
        "intercept",
        "z_speed",
        "body_ratio",
        "upper_wick_ratio",
        "lower_wick_ratio",
        "h1_aligned",
    }
    assert result["holdout_metrics"]["log_loss"] >= 0
    assert result["holdout_train_prevalence_baseline_metrics"]["brier_score"] >= 0


def test_logistic_returns_insufficient_data_for_too_small_sample():
    result = fit_evaluate_logistic(_rows(0, 10), _rows(300, 310))
    assert result["status"] == "INSUFFICIENT_DATA"


def test_logistic_rejects_invalid_feature_values():
    train = _rows(0, 40)
    train[0]["z_speed"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        fit_evaluate_logistic(train, _rows(300, 320))
