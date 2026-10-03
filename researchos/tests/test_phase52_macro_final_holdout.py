from __future__ import annotations

from researchos.experiments.phase52 import Phase52Config, run_phase52


def _inputs(n: int = 400):
    close = [100.0 + i * 0.01 for i in range(n)]
    high = [value + 1.0 for value in close]
    low = [value - 1.0 for value in close]
    volume = [1000.0 + i for i in range(n)]
    timestamps = list(range(n))
    macro = {
        symbol: [float(i) for i in range(n)]
        for symbol in ("DXY", "US10Y", "VIX")
    }
    macro_timestamps = {symbol: list(timestamps) for symbol in macro}
    return close, high, low, volume, timestamps, macro_timestamps, macro


def test_phase52_direct_path_cannot_bypass_independent_final_holdout() -> None:
    inputs = _inputs()
    result = run_phase52(
        *inputs[:4],
        inputs[6],
        config=Phase52Config(
            train_size=100,
            validation_size=50,
            step_size=50,
            holdout_size=20,
            feature_set="PRICE + DXY",
        ),
        timestamps=inputs[4],
        macro_timestamps=inputs[5],
    )

    assert result.outcome != "BLOCKED"
    metadata = result.metadata
    holdout = metadata["holdout"]

    assert holdout["holdout_events"] == 20
    assert holdout["prediction_count"] == 20
    assert holdout["fit_is_pre_holdout_only"] is True
    assert holdout["selection_frozen_before_scoring"] is True
    assert holdout["holdout_used_for_selection"] is False
    assert metadata["temporal_contract"]["holdout_excluded_from_wfo_aggregate"] is True
    assert metadata["calibration_contract"]["holdout_excluded"] is True
    assert all(
        fold["training_max_realized_end"] < fold["validation_start"]
        for fold in metadata["wfo_folds"]
    )
    assert all(
        fold["validation_realized_end"] < holdout["start"]
        for fold in metadata["wfo_folds"]
    )
    assert holdout["training_max_realized_end"] < holdout["start"]


def test_phase52_direct_path_requires_explicit_timestamp_contract() -> None:
    close, high, low, volume, _, _, macro = _inputs()
    result = run_phase52(
        close,
        high,
        low,
        volume,
        macro,
        config=Phase52Config(
            train_size=100,
            validation_size=50,
            step_size=50,
            holdout_size=20,
        ),
    )

    assert result.outcome == "BLOCKED"
    assert result.validation.data_valid is False
    assert result.validation.leakage_check is False
    assert result.validation.reproducible is True
