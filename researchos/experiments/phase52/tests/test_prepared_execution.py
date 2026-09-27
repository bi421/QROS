from __future__ import annotations

import pytest

from researchos.experiments.phase52 import Phase52Config
from researchos.experiments.phase52.comparison import run_phase52_comparison_optimized
from researchos.experiments.phase52.prepared import Phase52PreparedData


def _inputs(n: int = 1300):
    close = [100.0 + i * 0.01 for i in range(n)]
    high = [value + 1.0 for value in close]
    low = [value - 1.0 for value in close]
    volume = [1000.0 + i for i in range(n)]
    timestamps = list(range(n))
    macro = {symbol: [float(i) for i in range(n)] for symbol in ("DXY", "US10Y", "VIX")}
    macro_timestamps = {symbol: list(timestamps) for symbol in macro}
    return close, high, low, volume, timestamps, macro_timestamps, macro


def test_prepared_data_validates_identity_contract():
    inputs = _inputs()
    prepared = Phase52PreparedData.build(
        *inputs[:4], inputs[4], inputs[5], inputs[6], horizon=5, threshold=0.0
    )
    prepared.validate(("DXY", "US10Y", "VIX"))
    assert len(prepared.source_indices) == prepared.sample_count
    assert prepared.source_indices == tuple(sorted(set(prepared.source_indices)))
    assert prepared.input_provenance["combined_input_hash"]


def test_prepared_data_rejects_exact_timestamp_mismatch():
    inputs = _inputs()
    macro_timestamps = {symbol: list(values) for symbol, values in inputs[5].items()}
    macro_timestamps["VIX"][17] += 1
    with pytest.raises(ValueError, match="VIX"):
        Phase52PreparedData.build(
            *inputs[:4],
            inputs[4],
            macro_timestamps,
            inputs[6],
            horizon=5,
            threshold=0.0,
        )


def test_comparison_returns_all_feature_sets_from_one_prepared_dataset():
    inputs = _inputs()
    config = Phase52Config(train_size=1000, validation_size=200, step_size=200)
    results = run_phase52_comparison_optimized(
        *inputs[:4],
        inputs[6],
        config=config,
        timestamps=inputs[4],
        macro_timestamps=inputs[5],
    )
    assert set(results) == {
        "PRICE_ONLY",
        "PRICE + DXY",
        "PRICE + US10Y",
        "PRICE + VIX",
        "PRICE + ALL",
    }
    assert all(
        result.metadata.get("prepared_dataset_contract")
        == "single_materialized_dataset_shared_across_feature_sets"
        for result in results.values()
    )
    assert len({result.num_folds for result in results.values()}) == 1


def test_comparison_fails_closed_without_explicit_timestamps():
    inputs = _inputs()
    with pytest.raises(ValueError, match="timestamps"):
        run_phase52_comparison_optimized(*inputs[:4], inputs[6])


def test_prepared_data_blocks_when_samples_are_insufficient():
    inputs = _inputs(n=1250)
    prepared = Phase52PreparedData.build(
        *inputs[:4], inputs[4], inputs[5], inputs[6], horizon=5, threshold=0.0
    )
    result = prepared.blocked_if_insufficient(train_size=1000, validation_size=200)
    assert result is not None
    assert result.outcome == "BLOCKED"
    assert result.validation.outcome == "BLOCKED"
    assert result.validation.data_valid is False
    assert result.validation.leakage_check is False
    assert result.validation.out_of_sample is False
    assert result.validation.cost_adjusted is False
    assert result.validation.reproducible is True
    assert result.validation.reasons == (
        "REAL XAUUSD + MACRO DATA REQUIRED (insufficient aligned samples after merge)",
    )


def test_phase52_has_independent_temporal_holdout_and_excludes_it_from_wfo() -> None:
    inputs = _inputs(n=1400)
    config = Phase52Config(
        train_size=400,
        validation_size=100,
        step_size=100,
        holdout_size=40,
    )
    results = run_phase52_comparison_optimized(
        *inputs[:4],
        inputs[6],
        config=config,
        timestamps=inputs[4],
        macro_timestamps=inputs[5],
    )

    for result in results.values():
        metadata = result.metadata
        holdout = metadata["holdout"]
        temporal = metadata["temporal_contract"]
        calibration = metadata["calibration_contract"]

        assert holdout["holdout_events"] == 40
        assert holdout["prediction_count"] == 40
        assert holdout["fit_is_pre_holdout_only"] is True
        assert holdout["selection_frozen_before_scoring"] is True
        assert holdout["holdout_used_for_selection"] is False
        assert temporal["holdout_is_chronologically_disjoint"] is True
        assert temporal["holdout_excluded_from_wfo_aggregate"] is True
        assert calibration["holdout_excluded"] is True
        assert calibration["parameter_fitting_performed"] is False
        assert calibration["training_sample_count"] == result.model.sample_count
        assert holdout["model"]["sample_count"] == 40
        assert holdout["baseline"]["sample_count"] == 40

        assert (
            metadata["wfo_folds"][-1]["validation_end"]
            < holdout["start"]
        )
        assert holdout["training_max_realized_end"] < holdout["start"]
        assert all(
            fold["training_max_realized_end"] < fold["validation_start"]
            for fold in metadata["wfo_folds"]
        )
        assert all(
            fold["validation_realized_end"] < holdout["start"]
            for fold in metadata["wfo_folds"]
        )


def test_phase52_holdout_boundaries_and_predictions_are_deterministic() -> None:
    inputs = _inputs(n=1400)
    config = Phase52Config(
        train_size=400,
        validation_size=100,
        step_size=100,
        holdout_size=40,
    )
    first = run_phase52_comparison_optimized(
        *inputs[:4],
        inputs[6],
        config=config,
        timestamps=inputs[4],
        macro_timestamps=inputs[5],
    )
    second = run_phase52_comparison_optimized(
        *inputs[:4],
        inputs[6],
        config=config,
        timestamps=inputs[4],
        macro_timestamps=inputs[5],
    )

    for feature_set in first:
        assert first[feature_set].metadata["wfo_folds"] == second[feature_set].metadata["wfo_folds"]
        assert first[feature_set].metadata["holdout"] == second[feature_set].metadata["holdout"]


def test_phase52_rejects_nonpositive_final_holdout_size() -> None:
    inputs = _inputs()
    with pytest.raises(ValueError, match="holdout_size must be positive"):
        run_phase52_comparison_optimized(
            *inputs[:4],
            inputs[6],
            config=Phase52Config(
                train_size=400,
                validation_size=100,
                step_size=100,
                holdout_size=0,
            ),
            timestamps=inputs[4],
            macro_timestamps=inputs[5],
        )
