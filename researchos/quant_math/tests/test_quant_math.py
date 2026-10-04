import math
import pytest
from researchos.quant_math import QuantMathEngine,Vector2D,curvature_three_points,measure_market_geometry

def test_geometry():
    r=measure_market_geometry([1,2,3,4])
    assert r.slope==pytest.approx(1.0)
    assert r.angle_degrees==pytest.approx(45.0)
    assert r.distance==pytest.approx(math.sqrt(18))
    assert r.trend_r2==pytest.approx(1.0)

def test_geometry_primitives():
    assert Vector2D(1,2).dot(Vector2D(4,6))==pytest.approx(16)
    assert curvature_three_points(Vector2D(0,0),Vector2D(1,1),Vector2D(2,0))<0

def test_full_engine_is_deterministic():
    e=QuantMathEngine()
    a=e.evaluate([100,101,102,101],7,3,25)
    b=e.evaluate([100,101,102,101],7,3,25)
    assert a.result_hash==b.result_hash
    assert a.bayesian is not None
    assert a.bayesian.posterior_mean==pytest.approx(0.8*0.8333333333333334) or a.bayesian.posterior_mean==pytest.approx(0.8)

def test_rejects_partial_bayes():
    with pytest.raises(ValueError): QuantMathEngine().evaluate([1,2],1,None)
