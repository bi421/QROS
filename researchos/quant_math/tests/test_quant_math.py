import math

import pytest

from researchos.quant_math import (
    QuantMathEngine,
    Vector2D,
    curvature_three_points,
    measure_market_geometry,
)


def test_geometry():
    result = measure_market_geometry([1, 2, 3, 4])
    assert result.slope == pytest.approx(1.0)
    assert result.angle_degrees == pytest.approx(45.0)
    assert result.distance == pytest.approx(math.sqrt(18))
    assert result.trend_r2 == pytest.approx(1.0)


def test_geometry_primitives():
    assert Vector2D(1, 2).dot(Vector2D(4, 6)) == pytest.approx(16)
    assert curvature_three_points(
        Vector2D(0, 0),
        Vector2D(1, 1),
        Vector2D(2, 0),
    ) < 0


def test_full_engine_is_deterministic():
    engine = QuantMathEngine()
    first = engine.evaluate([100, 101, 102, 101], 7, 3, 25)
    second = engine.evaluate([100, 101, 102, 101], 7, 3, 25)
    assert first.result_hash == second.result_hash
    assert first.bayesian is not None
    assert (
        first.bayesian.posterior_mean
        == pytest.approx(0.8 * 0.8333333333333334)
        or first.bayesian.posterior_mean == pytest.approx(0.8)
    )


def test_rejects_partial_bayes():
    with pytest.raises(ValueError):
        QuantMathEngine().evaluate([1, 2], 1, None)
