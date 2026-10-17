import numpy as np
import pytest

from researchos.orchestration.incremental_regime import IncrementalRegimeEngine


def test_incremental_engine_warms_up_then_returns_three_state_probability_contract():
    engine = IncrementalRegimeEngine(lookback=40, adx_period=5, hurst_refresh_every=5)
    rng = np.random.default_rng(42)
    close = 2000.0

    results = []
    for _ in range(160):
        close *= float(np.exp(rng.normal(0.0001, 0.002)))
        result = engine.update(close + 1.0, close - 1.0, close)
        if result is not None:
            results.append(result)

    assert results
    result = results[-1]
    assert result["status"] == "CLASSIFIED"
    assert result["current_state"] in {"UP", "DOWN", "RANGE"}
    assert set(result["state_probabilities_next"]) == {"UP", "DOWN", "RANGE"}
    assert sum(result["state_probabilities_next"].values()) == pytest.approx(1.0)
    assert result["execution_enabled"] is False
    assert result["bar_count_seen"] == 160


def test_incremental_engine_matches_batch_adx_and_price_slope():
    import pandas as pd

    from researchos.orchestration.xauusd_regime_detection import detect_market_regime

    rng = np.random.default_rng(19)
    close = 2000.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.001, 180)))
    frame = pd.DataFrame({"high": close + 1.0, "low": close - 1.0, "close": close})
    batch = detect_market_regime(frame, lookback=40, adx_period=5)
    engine = IncrementalRegimeEngine(lookback=40, adx_period=5, hurst_refresh_every=1)
    incremental = None
    for row in frame.itertuples(index=False):
        incremental = engine.update(row.high, row.low, row.close)

    assert incremental is not None
    assert incremental["current_state"] == batch["current_state"]
    assert incremental["features"]["adx"] == pytest.approx(batch["features"]["adx"], abs=1e-9)
    assert incremental["features"]["normalized_log_price_slope"] == pytest.approx(
        batch["features"]["normalized_log_price_slope"], abs=1e-9
    )


def test_incremental_engine_rejects_invalid_candle():
    engine = IncrementalRegimeEngine(lookback=40, adx_period=5)
    with pytest.raises(ValueError, match="invalid OHLC"):
        engine.update(100.0, 101.0, 100.5)


def test_incremental_engine_rolling_state_stays_bounded():
    engine = IncrementalRegimeEngine(lookback=40, adx_period=5, hurst_refresh_every=3)
    close = 2000.0
    for index in range(500):
        close += 0.1 if index % 3 else -0.05
        engine.update(close + 1.0, close - 1.0, close)

    assert len(engine.log_closes) == 40
    assert len(engine.log_returns) == 39
    assert len(engine.true_ranges) == 5
    assert len(engine.dx_values) <= 5
