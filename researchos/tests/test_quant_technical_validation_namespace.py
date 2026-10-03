from __future__ import annotations

import math

import pytest

from researchos.engines.quant.technical.contracts import Bars as LegacyBars
from researchos.engines.quant.technical.validation import (
    validate_bars as legacy_validate_bars,
    validate_params as legacy_validate_params,
    validate_period as legacy_validate_period,
    validate_positive_float as legacy_validate_positive_float,
)
from researchos.quant_engine.technical.contracts import Bars
from researchos.quant_engine.technical.validation import (
    validate_bars,
    validate_params,
    validate_period,
    validate_positive_float,
)


def _bars(value: object = 1.0) -> Bars:
    values = [value]
    return Bars(open=values, high=values, low=values, close=values, volume=values)


def _legacy_bars(value: object = 1.0) -> LegacyBars:
    values = [value]
    return LegacyBars(open=values, high=values, low=values, close=values, volume=values)


def test_validation_namespace_uses_canonical_implementation() -> None:
    assert legacy_validate_bars is validate_bars
    assert legacy_validate_period is validate_period
    assert legacy_validate_positive_float is validate_positive_float
    assert legacy_validate_params is validate_params


def test_validate_bars_representative_behavior() -> None:
    validate_bars(_bars())
    legacy_validate_bars(_legacy_bars())

    with pytest.raises(ValueError, match="empty bar series"):
        validate_bars(Bars())
    with pytest.raises(ValueError, match="empty bar series"):
        legacy_validate_bars(LegacyBars())

    for factory in (_bars, _legacy_bars):
        with pytest.raises(ValueError, match="contains None"):
            validate_bars(factory(None))
        with pytest.raises(TypeError, match="must contain numeric values"):
            validate_bars(factory("bad"))
        with pytest.raises(ValueError, match="contains NaN"):
            validate_bars(factory(float("nan")))


def test_validate_bars_propagates_bars_validate_error() -> None:
    bars = Bars(open=[1.0, 2.0], high=[1.0], low=[1.0, 2.0], close=[1.0, 2.0], volume=[1.0, 2.0])
    legacy_bars = LegacyBars(
        open=[1.0, 2.0],
        high=[1.0],
        low=[1.0, 2.0],
        close=[1.0, 2.0],
        volume=[1.0, 2.0],
    )
    with pytest.raises(ValueError, match="equal length"):
        validate_bars(bars)
    with pytest.raises(ValueError, match="equal length"):
        legacy_validate_bars(legacy_bars)


def test_validate_period_defaults_coercion_and_invalid_values() -> None:
    assert validate_period(None) == 14
    assert legacy_validate_period(None) == 14
    assert validate_period(7.9) == 7
    assert legacy_validate_period(7.9) == 7

    for fn in (validate_period, legacy_validate_period):
        with pytest.raises(TypeError, match="period must be numeric"):
            fn("14")
        with pytest.raises(ValueError, match="period must be positive"):
            fn(0)
        with pytest.raises(ValueError, match="period must be positive"):
            fn(-2)


def test_validate_positive_float_defaults_coercion_and_invalid_values() -> None:
    assert validate_positive_float("multiplier", None, 2.5) == 2.5
    assert legacy_validate_positive_float("multiplier", None, 2.5) == 2.5
    assert validate_positive_float("multiplier", 3, 2.5) == 3.0
    assert legacy_validate_positive_float("multiplier", 3, 2.5) == 3.0

    for fn in (validate_positive_float, legacy_validate_positive_float):
        with pytest.raises(TypeError, match="must be numeric"):
            fn("multiplier", "3", 2.5)
        with pytest.raises(ValueError, match="must be positive"):
            fn("multiplier", 0, 2.5)
        with pytest.raises(ValueError, match="must be positive"):
            fn("multiplier", -1.0, 2.5)


def test_validate_params_defaults_and_unknown_parameter_rejection() -> None:
    allowed = {"period": 14, "multiplier": 2.0}
    params = {"period": 7}
    assert validate_params(params, allowed) == {"period": 7, "multiplier": 2.0}
    assert legacy_validate_params(params, allowed) == {"period": 7, "multiplier": 2.0}

    for fn in (validate_params, legacy_validate_params):
        with pytest.raises(ValueError, match="Unknown indicator parameters"):
            fn({"unknown": 1}, allowed)


def test_validation_outputs_are_deterministic() -> None:
    bars = _bars()
    assert validate_period(14) == validate_period(14)
    assert validate_positive_float("x", 1, 2.0) == validate_positive_float("x", 1, 2.0)
    assert validate_params({"period": 14}, {"period": 10}) == {"period": 14}
    assert math.isfinite(float(bars.close[0]))
