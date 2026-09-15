"""Regression tests for Phase 5.2 feature-set isolation."""

from __future__ import annotations

import pytest

from researchos.experiments.phase52 import FEATURE_SET_NAMES, Phase52Config, run_phase52_comparison
from researchos.experiments.phase52.multivariate import MultivariateEmpiricalProbabilityEstimator
from researchos.experiments.phase52.tests.test_phase52 import _run_inputs


def test_multivariate_estimator_uses_all_selected_features():
    features = [(0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)]
    labels = [-1.0, 1.0, 1.0, -1.0]
    est_a = MultivariateEmpiricalProbabilityEstimator(feature_indices=(0, 1), n_neighbors=1).fit(features, labels)
    est_b = MultivariateEmpiricalProbabilityEstimator(feature_indices=(0,), n_neighbors=1).fit(features, labels)
    row = (0.0, 1.0)
    assert est_a.predict_class(row) == 1
    assert est_b.predict_class(row) == -1


@pytest.mark.frozen
def test_phase52_comparison_returns_all_isolated_feature_sets():
    close, high, low, volume, macro, ts, macro_ts = _run_inputs()
    cfg = Phase52Config(train_size=400, validation_size=100, step_size=100, n_neighbors=25)
    results = run_phase52_comparison(close, high, low, volume, macro, config=cfg, timestamps=ts, macro_timestamps=macro_ts)
    assert tuple(results) == FEATURE_SET_NAMES
    assert all(result.outcome != "BLOCKED" for result in results.values())
    assert {result.metadata["feature_set"] for result in results.values()} == set(FEATURE_SET_NAMES)
    assert all(result.metadata["num_folds"] == next(iter(results.values())).metadata["num_folds"] for result in results.values())
    assert results["PRICE_ONLY"].metadata["selected_feature_names"]
    assert all(name.startswith("macro_DXY_") for name in results["PRICE + DXY"].metadata["selected_feature_names"][-3:])
    assert all(name.startswith("macro_US10Y_") for name in results["PRICE + US10Y"].metadata["selected_feature_names"][-3:])
    assert all(name.startswith("macro_VIX_") for name in results["PRICE + VIX"].metadata["selected_feature_names"][-3:])
    assert len(results["PRICE + ALL"].metadata["selected_feature_names"]) == len(results["PRICE_ONLY"].metadata["selected_feature_names"]) + 9


@pytest.mark.frozen
def test_phase52_comparison_is_deterministic():
    close, high, low, volume, macro, ts, macro_ts = _run_inputs()
    cfg = Phase52Config(train_size=400, validation_size=100, step_size=100)
    first = run_phase52_comparison(close, high, low, volume, macro, config=cfg, timestamps=ts, macro_timestamps=macro_ts)
    second = run_phase52_comparison(close, high, low, volume, macro, config=cfg, timestamps=ts, macro_timestamps=macro_ts)
    assert {k: v.to_dict() for k, v in first.items()} == {k: v.to_dict() for k, v in second.items()}
