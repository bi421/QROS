from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from researchos.orchestration.incremental_regime import IncrementalRegimeEngine
from researchos.orchestration.regime_hypothesis import evaluate_regime_directional_value
from scripts.run_xauusd_regime_hypothesis import run_test


@given(
    st.lists(
        st.floats(min_value=100.0, max_value=10_000.0, allow_nan=False, allow_infinity=False),
        min_size=40,
        max_size=180,
    )
)
@settings(max_examples=40, deadline=None)
def test_incremental_engine_never_emits_invalid_probability_simplex(closes):
    engine = IncrementalRegimeEngine(lookback=40, adx_period=5, hurst_refresh_every=10)
    last = None
    for close in closes:
        last = engine.update(close * 1.001, close * 0.999, close)
    if last is not None:
        probabilities = last["state_probabilities_next"]
        assert set(probabilities) == {"UP", "DOWN", "RANGE"}
        assert all(np.isfinite(value) and 0 <= value <= 1 for value in probabilities.values())
        assert sum(probabilities.values()) == pytest.approx(1.0)
        assert last["execution_enabled"] is False


def test_hypothesis_test_detects_a_strong_synthetic_directional_signal():
    rng = np.random.default_rng(71)
    returns = rng.normal(0.0, 0.0001, 3000)
    returns[1500:] += 0.001
    closes = 2000.0 * np.exp(np.cumsum(returns))
    states = ["RANGE"] * 3000
    states[1500:] = ["UP"] * 1500

    report = evaluate_regime_directional_value(
        states,
        closes,
        horizon=1,
        holdout_fraction=0.3,
        block_length=5,
        bootstrap_replicates=399,
        seed=13,
    )
    assert report["status"] == "COMPLETED"
    assert report["alpha_0_05_reject_null"] is True
    assert report["ci_95_percent"][0] > 0
    assert report["execution_enabled"] is False


def test_hypothesis_test_reports_insufficient_evidence_for_short_series():
    report = evaluate_regime_directional_value(
        ["RANGE"] * 60,
        np.linspace(2000, 2001, 60),
        horizon=5,
        bootstrap_replicates=199,
    )
    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["execution_enabled"] is False


def test_hypothesis_cli_streams_and_bounds_tail_buffer(tmp_path: Path):
    source = tmp_path / "candles.csv"
    count = 500
    timestamps = pd.date_range("2026-01-01", periods=count, freq="min", tz="UTC")
    close = 2000.0 * np.exp(np.cumsum(np.full(count, 0.0001)))
    pd.DataFrame(
        {
            "timestamp": timestamps,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
        }
    ).to_csv(source, index=False)

    result = run_test(
        source,
        chunksize=37,
        horizon=2,
        max_observations=100,
        bootstrap_replicates=199,
        lookback=40,
        adx_period=5,
    )
    assert result["input"]["row_count_processed"] == count
    assert result["input"]["tail_buffer_rows_retained"] <= 2 * 100 + 2 + 1
    assert result["resource_policy"]["network_access"] is False
    assert result["resource_policy"]["database_access"] is False
    assert result["resource_policy"]["order_execution"] is False


def test_hypothesis_cli_rejects_duplicate_timestamps_across_chunks(tmp_path: Path):
    source = tmp_path / "duplicate.csv"
    pd.DataFrame(
        {
            "timestamp": [
                "2026-01-01T00:00:00Z",
                "2026-01-01T01:00:00Z",
                "2026-01-01T01:00:00Z",
            ],
            "high": [2002, 2003, 2004],
            "low": [1998, 1999, 2000],
            "close": [2000, 2001, 2002],
        }
    ).to_csv(source, index=False)
    with pytest.raises(ValueError, match="duplicate or not chronological"):
        run_test(
            source,
            chunksize=2,
            horizon=1,
            max_observations=100,
            bootstrap_replicates=199,
            lookback=40,
            adx_period=5,
        )
