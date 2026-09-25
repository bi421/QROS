"""Focused compatibility and behavior tests for technical indicators."""

import math

import pytest

from researchos.engines.quant.technical import indicators as legacy
from researchos.quant_engine.technical import indicators as canonical
from researchos.quant_engine.technical.contracts import Bars


_PUBLIC = [
    "sma",
    "ema",
    "wma",
    "hma",
    "vwma",
    "rsi",
    "stochastic",
    "cci",
    "roc",
    "momentum",
    "atr",
    "bollinger_bands",
    "keltner_channel",
    "donchian_channel",
    "obv",
    "vwap",
    "mfi",
    "cmf",
    "accumulation_distribution",
    "dmi",
    "adx",
    "macd",
    "supertrend",
    "ichimoku_cloud",
    "parabolic_sar",
]


def _bars(length: int = 60) -> Bars:
    opens = [100.0 + i * 0.5 for i in range(length)]
    return Bars(
        open=opens,
        high=[value + 1.5 for value in opens],
        low=[value - 1.0 for value in opens],
        close=[value + 0.5 for value in opens],
        volume=[1000.0 + i * 10.0 for i in range(length)],
    )


def test_legacy_public_indicator_api_is_canonical() -> None:
    assert legacy.__all__ == _PUBLIC
    assert canonical.sma is legacy.sma
    for name in _PUBLIC:
        assert getattr(legacy, name) is getattr(canonical, name)


def test_representative_indicator_values_and_shapes() -> None:
    bars = _bars(30)

    assert canonical.sma(bars, 3)[2] == pytest.approx(sum(bars.close[:3]) / 3.0)
    assert canonical.ema(bars, 3)[0] == pytest.approx(bars.close[0])
    assert canonical.wma(bars, 3)[2] == pytest.approx(
        (bars.close[2] * 3 + bars.close[1] * 2 + bars.close[0]) / 6.0
    )
    assert canonical.roc(bars, 3)[3] == pytest.approx(
        (bars.close[3] - bars.close[0]) / bars.close[0] * 100.0
    )
    assert canonical.momentum(bars, 3)[3] == pytest.approx(bars.close[3] - bars.close[0])

    for result in (
        canonical.bollinger_bands(bars, 5),
        canonical.keltner_channel(bars, 5, 3),
        canonical.donchian_channel(bars, 5),
        canonical.dmi(bars, 5),
        canonical.macd(bars),
        canonical.supertrend(bars, 5, 2.0),
        canonical.ichimoku_cloud(bars),
        canonical.parabolic_sar(bars),
    ):
        assert all(len(series) == bars.length for series in result.values())


def test_empty_and_insufficient_inputs_preserve_indicator_contract() -> None:
    empty = Bars()
    assert canonical.sma(empty) == []
    assert canonical.ema(empty) == []
    assert canonical.atr(empty) == []

    short = _bars(2)
    assert canonical.sma(short, 5) == [None, None]
    assert canonical.wma(short, 5) == [None, None]
    assert canonical.bollinger_bands(short, 5) == {
        "upper": [None, None],
        "middle": [None, None],
        "lower": [None, None],
    }


def test_boundary_parameters_and_nonfinite_values_are_deterministic() -> None:
    bars = _bars(5)
    assert canonical.sma(bars, 0) == [None] * bars.length
    assert canonical.wma(bars, 0) == [None] * bars.length

    nan_bars = Bars(
        open=[1.0, 2.0],
        high=[2.0, 3.0],
        low=[0.0, 1.0],
        close=[1.0, math.nan],
        volume=[10.0, 20.0],
    )
    first = canonical.sma(nan_bars, 2)
    second = canonical.sma(nan_bars, 2)
    assert math.isnan(first[1])
    assert math.isnan(second[1])

    inf_bars = Bars(
        open=[1.0, 2.0],
        high=[2.0, 3.0],
        low=[0.0, 1.0],
        close=[1.0, math.inf],
        volume=[10.0, 20.0],
    )
    assert math.isinf(canonical.sma(inf_bars, 2)[1])


def test_indicator_outputs_do_not_mutate_bars() -> None:
    bars = _bars(20)
    before = {
        "open": list(bars.open),
        "high": list(bars.high),
        "low": list(bars.low),
        "close": list(bars.close),
        "volume": list(bars.volume),
    }

    canonical.rsi(bars)
    canonical.stochastic(bars)
    canonical.macd(bars)
    canonical.supertrend(bars)

    assert bars.open == before["open"]
    assert bars.high == before["high"]
    assert bars.low == before["low"]
    assert bars.close == before["close"]
    assert bars.volume == before["volume"]


def test_repeated_indicator_calls_are_deterministic() -> None:
    bars = _bars(60)
    for name in _PUBLIC:
        fn = getattr(canonical, name)
        first = fn(bars)
        second = fn(bars)
        assert first == second
