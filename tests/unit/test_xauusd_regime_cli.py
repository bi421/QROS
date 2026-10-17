from pathlib import Path
import pandas as pd
import pytest
from scripts.run_xauusd_regime_detection import _load_candles


def test_loader_rejects_duplicate_timestamps(tmp_path: Path):
    source = tmp_path / "dupes.csv"
    pd.DataFrame(
        {
            "timestamp": ["2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"],
            "high": [2, 3],
            "low": [1, 2],
            "close": [1.5, 2.5],
        }
    ).to_csv(source, index=False)
    with pytest.raises(ValueError, match="duplicate timestamps"):
        _load_candles(source)


def test_walk_forward_audit_uses_training_transition_counts():
    from scripts.run_xauusd_regime_detection import _walk_forward_transition_audit

    labels = ["UP", "UP", "DOWN", "DOWN", "UP", "UP", "RANGE", "RANGE", "UP", "DOWN"] * 10
    result = _walk_forward_transition_audit(labels, train_fraction=0.7)

    assert result["status"] == "MEASURED_OUT_OF_SAMPLE_NOT_CALIBRATED"
    assert result["test_transition_count"] > 0
    assert result["confidence_intervals"] == "NOT_COMPUTED"
    assert result["trading_edge_proven"] is False


def test_forward_return_audit_is_descriptive_and_holdout_only():
    from scripts.run_xauusd_regime_detection import _forward_return_audit

    candles = pd.DataFrame({"close": [100.0 + i for i in range(30)]})
    labels = ["UP"] * 30
    result = _forward_return_audit(candles, labels, train_fraction=0.7, horizons=(1, 5))

    assert result["status"] == "DESCRIPTIVE_HOLDOUT_MEASUREMENTS_NOT_EDGE_PROOF"
    assert result["horizons"]["1"]["by_state"]["UP"]["sample_count"] == 8
    assert result["horizons"]["1"]["by_state"]["UP"]["directional_hit_rate"] == 1.0
    assert result["trading_edge_proven"] is False
