"""Deterministic C++ backtest regression tests.

These tests deliberately use an in-repository deterministic price fixture rather
than user-local XAUUSD files. The purpose is to verify the compiled C++ backend's
numeric contract and parity with independently calculated Python references.
They do not claim anything about XAUUSD or trading performance.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from researchos.quant_engine.cpp_backend import CppQuantAdapter
from researchos.quant_engine.backend import PythonQuantBackend

SMA_FAST = 20
SMA_SLOW = 50
ATOL = 1e-12
RTOL = 1e-10


@pytest.fixture(scope="module")
def cpp_engine() -> CppQuantAdapter:
    engine = CppQuantAdapter()

    if not engine.is_cpp:
        pytest.fail(
            "C++ Quant Engine is not active. Refusing to run a C++ regression "
            "test against Python fallback."
        )

    return engine


def load_regression_daily() -> pd.DataFrame:
    """Return a deterministic daily price fixture with repeated SMA crossings."""
    periods = 320
    i = np.arange(periods, dtype=float)
    close = 100.0 + 0.04 * i + 7.5 * np.sin(i / 5.0) + 2.0 * np.sin(i / 13.0)

    index = pd.date_range("2020-01-01", periods=periods, freq="D")
    daily = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(periods, 1000.0),
        },
        index=index,
    )

    assert len(daily) > SMA_SLOW + 2
    assert np.isfinite(daily["close"].to_numpy()).all()
    return daily


def build_sma_strategy(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, int]:
    data = df.copy()
    data["sma20"] = data["close"].rolling(SMA_FAST).mean()
    data["sma50"] = data["close"].rolling(SMA_SLOW).mean()
    data = data.dropna(subset=["sma20", "sma50"]).copy()

    data["signal"] = np.where(data["sma20"] > data["sma50"], 1.0, -1.0)

    # Next-bar execution prevents same-bar look-ahead.
    data["position"] = data["signal"].shift(1).fillna(0.0)
    data["market_return"] = data["close"].pct_change().fillna(0.0)
    data["strategy_return"] = data["position"] * data["market_return"]

    returns = data["strategy_return"].iloc[1:].astype(float)
    if returns.empty:
        pytest.fail("SMA20/50 produced no strategy returns.")
    if not np.isfinite(returns.to_numpy()).all():
        pytest.fail("SMA20/50 produced NaN or infinite returns.")

    position_changes = data["position"].diff().fillna(0.0).abs()
    trades = int((position_changes > 0.0).sum())
    return data, returns, trades


def build_equity_curve(returns: pd.Series, initial_capital: float = 100000.0) -> list[float]:
    equity_curve = [initial_capital]
    for value in returns.to_numpy(dtype=float):
        equity_curve.append(equity_curve[-1] * (1.0 + float(value)))
    return equity_curve


def run_cpp_metrics(engine: CppQuantAdapter, returns: pd.Series) -> dict:
    values = [float(x) for x in returns.to_numpy()]
    if len(values) < 2:
        pytest.fail("Not enough strategy returns.")
    if not np.isfinite(np.asarray(values)).all():
        pytest.fail("Strategy returns contain non-finite values.")

    equity_curve = build_equity_curve(returns)
    prices = [1.0]
    for value in values:
        prices.append(prices[-1] * (1.0 + value))

    cpp_returns = engine.calculate_returns(prices, return_type="percentage")
    statistics = engine.calculate_statistics(values)
    metrics = engine.calculate_metrics(values, equity_curve, risk_free_rate=0.0)

    assert cpp_returns
    assert statistics
    assert metrics

    return {
        "cpp_returns": cpp_returns,
        "statistics": statistics,
        "metrics": metrics,
        "equity_curve": equity_curve,
    }


def calculate_reference_statistics(returns: pd.Series) -> dict[str, float]:
    values = returns.to_numpy(dtype=float)
    return {
        "count": float(len(values)),
        "mean": float(np.mean(values)),
        "sum": float(np.sum(values)),
        "std": float(np.std(values, ddof=1)),
    }


def calculate_reference_max_drawdown(equity_curve: list[float]) -> float:
    equity = np.asarray(equity_curve, dtype=float)
    peaks = np.maximum.accumulate(equity)
    drawdowns = (equity - peaks) / peaks
    return float(np.min(drawdowns))


def calculate_reference_metrics(returns: pd.Series, equity_curve: list[float]) -> dict[str, float]:
    values = returns.to_numpy(dtype=float)
    mean_return = float(np.mean(values))
    std_return = float(np.std(values, ddof=1))
    negative = values[values < 0.0]
    downside = float(np.std(negative, ddof=1)) if len(negative) >= 2 else 0.0
    wins = values[values > 0.0]
    losses = values[values < 0.0]
    profit_factor = (
        float(np.sum(wins) / abs(np.sum(losses)))
        if len(losses) and np.sum(losses) != 0.0
        else (float("inf") if len(wins) else 0.0)
    )
    max_drawdown = round(calculate_reference_max_drawdown(equity_curve), 8)

    return {
        "total_return": float(np.sum(values)),
        "mean_return": mean_return,
        "std_return": std_return,
        "downside_deviation": downside,
        "max_drawdown": max_drawdown,
        "win_rate": float(np.sum(values > 0.0) / len(values)),
        "profit_factor": profit_factor,
        "annualised_return": mean_return * 252.0,
        "annualised_volatility": std_return * np.sqrt(252.0),
    }


def test_cpp_engine_is_active(cpp_engine: CppQuantAdapter):
    assert cpp_engine.is_cpp is True
    version = cpp_engine.get_version()
    assert version
    assert version != "python_fallback"


def test_cpp_percentage_return_contract(cpp_engine: CppQuantAdapter):
    prices = [100.0, 102.0, 101.0, 105.0]
    expected = [0.02, -1.0 / 102.0, 4.0 / 101.0]

    actual = cpp_engine.calculate_returns(prices, "percentage")
    assert actual == pytest.approx(expected, abs=ATOL)


def test_sma_20_50_numeric_parity(cpp_engine: CppQuantAdapter):
    df = load_regression_daily()
    _, returns, trades = build_sma_strategy(df)
    assert trades >= 5

    result = run_cpp_metrics(cpp_engine, returns)
    statistics = result["statistics"]
    metrics = result["metrics"]
    equity_curve = result["equity_curve"]

    reference_statistics = calculate_reference_statistics(returns)
    reference_metrics = calculate_reference_metrics(returns, equity_curve)

    for key, expected in reference_statistics.items():
        assert float(statistics[key]) == pytest.approx(expected, rel=RTOL, abs=ATOL), key

    for key, expected in reference_metrics.items():
        actual = float(metrics[key])
        if np.isinf(expected):
            assert np.isinf(actual)
        else:
            assert actual == pytest.approx(expected, rel=RTOL, abs=ATOL), key


def test_cpp_returns_match_reference_series(cpp_engine: CppQuantAdapter):
    df = load_regression_daily()
    _, returns, trades = build_sma_strategy(df)
    assert trades >= 5

    result = run_cpp_metrics(cpp_engine, returns)
    expected = [float(x) for x in returns.to_numpy()]

    # calculate_returns is a fraction-return API; prices are reconstructed from
    # the same independent Python strategy returns, so this checks every output.
    actual = result["cpp_returns"]
    assert len(actual) == len(expected)
    assert actual == pytest.approx(expected, rel=RTOL, abs=ATOL)


def test_python_reference_contract_is_independent(cpp_engine: CppQuantAdapter):
    """Keep the reference calculation independent of C++ implementation code."""
    df = load_regression_daily()
    _, returns, trades = build_sma_strategy(df)
    assert trades >= 5

    # Explicitly compare against the frozen Python backend's return contract as
    # a second implementation boundary; C++ must match the same public units.
    prices = [100.0, 102.0, 101.0, 105.0]
    python_returns = PythonQuantBackend().calculate_returns(prices, "percentage")
    cpp_returns = cpp_engine.calculate_returns(prices, "percentage")
    assert cpp_returns == pytest.approx(python_returns, rel=RTOL, abs=ATOL)
