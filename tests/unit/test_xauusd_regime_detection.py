import numpy as np
import pandas as pd
import pytest

from researchos.orchestration.xauusd_regime_detection import (
    STATES,
    detect_market_regime,
)


def _candles(n: int = 260, drift: float = 0.001) -> pd.DataFrame:
    rng = np.random.default_rng(17)
    returns = drift + rng.normal(0, 0.001, n)
    close = 2000 * np.exp(np.cumsum(returns))
    spread = np.full(n, 1.5)
    return pd.DataFrame({"high": close + spread, "low": close - spread, "close": close})


def test_returns_three_state_contract_and_probabilities_sum_to_one():
    result = detect_market_regime(_candles())

    assert result["status"] == "CLASSIFIED"
    assert result["current_state"] in STATES
    assert set(result["state_probabilities_next"]) == set(STATES)
    assert sum(result["state_probabilities_next"].values()) == pytest.approx(1.0)
    assert result["execution_enabled"] is False
    assert result["probability_status"] == "SMOOTHED_EMPIRICAL_FREQUENCY_NOT_CALIBRATED"


def test_short_history_fails_closed():
    with pytest.raises(ValueError, match="INSUFFICIENT_HISTORY"):
        detect_market_regime(_candles(50))


def test_invalid_ohlc_fails_closed():
    candles = _candles()
    candles.loc[0, "high"] = candles.loc[0, "low"] - 1

    with pytest.raises(ValueError, match="invalid OHLC"):
        detect_market_regime(candles)


def test_transition_probabilities_are_deterministic():
    candles = _candles(drift=-0.0002)
    first = detect_market_regime(candles)
    second = detect_market_regime(candles)

    assert first == second
