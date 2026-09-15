"""Additional regression coverage for Phase 5.2 feature-set isolation."""

from __future__ import annotations

import pytest

from researchos.experiments.phase52 import FEATURE_SET_NAMES, Phase52Config, run_phase52_comparison
from researchos.experiments.phase52.multivariate import MultivariateEmpiricalProbabilityEstimator
from researchos.experiments.phase52.tests.test_phase52 import _run_inputs


def test_multivariate_estimator_uses_all_selected_features():
    features = [(0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)]
    labels = [-1.0, 1.0, 1.0, -1.0]
    two_dim = MultivariateEmpiricalProbabilityEstimator(feature_indices=(0, 1), n_neighbors=1).fit(features, labels)
    one_dim = MultivariateEmpiricalProbabilityEstimator(feature_indices=(0,), n_neighbors=1).fit(features, labels)
    assert two_dim.predict_class((0.0, 1.0)) == 1
    assert one_dim.predict_class((0.0, 1.0)) == -1


@pytest.mark.frozen
def test_comparison_has_identical_fold_geometry_and_explicit_feature_sets():
    close, high, low, volume, macro, ts, macro_ts = _run_inputs()
    results = run_phase52_comparison(close, high, low, volume, macro, config=Phase52Config(train_size=400, validation_size=100, step_size=100), timestamps=ts, macro_timestamps=macro_ts)
    assert tuple(results) == FEATURE_SET_NAMES
    assert all(result.outcome != "BLOCKED" for result in results.values())
    assert len({result.num_folds for result in results.values()}) == 1
    assert results["PRICE_ONLY"].metadata["selected_feature_indices"] == list(range(19))
    assert len(results["PRICE + DXY"].metadata["selected_feature_indices"]) == 22
    assert len(results["PRICE + US10Y"].metadata["selected_feature_indices"]) == 22
    assert len(results["PRICE + VIX"].metadata["selected_feature_indices"]) == 22
    assert len(results["PRICE + ALL"].metadata["selected_feature_indices"]) == 28


@pytest.mark.frozen
def test_comparison_is_reproducible():
    close, high, low, volume, macro, ts, macro_ts = _run_inputs()
    cfg = Phase52Config(train_size=400, validation_size=100, step_size=100)
    first = run_phase52_comparison(close, high, low, volume, macro, config=cfg, timestamps=ts, macro_timestamps=macro_ts)
    second = run_phase52_comparison(close, high, low, volume, macro, config=cfg, timestamps=ts, macro_timestamps=macro_ts)
    assert {key: value.reproducibility_hash for key, value in first.items()} == {key: value.reproducibility_hash for key, value in second.items()}
