import numpy as np
import pytest

try:
    from cpp_quant_engine.cpp_quant_backend import (
        candle_geometry,
        geometric_interval_probability,
        first_passage_probability,
        empirical_edge,
    )
except ImportError:
    candle_geometry = None
    geometric_interval_probability = None
    first_passage_probability = None
    empirical_edge = None

pytestmark = pytest.mark.skipif(
    candle_geometry is None
    or geometric_interval_probability is None
    or first_passage_probability is None
    or empirical_edge is None,
    reason="compiled nanobind Quant Engine is unavailable",
)

def test_candle_geometry_writes_caller_owned_array():
    o=np.asarray([97.,90.]); h=np.asarray([100.,100.]); l=np.asarray([90.,80.]); c=np.asarray([98.,85.])
    out=np.empty((2,5),dtype=np.float64)
    candle_geometry(o,h,l,c,out)
    np.testing.assert_allclose(out, [[10,.1,.2,.7,.8],[20,.25,.25,.25,.25]], rtol=0, atol=0)

def test_geometric_null_and_first_passage():
    l=np.asarray([90.]); h=np.asarray([100.]); p1=np.asarray([90.]); p2=np.asarray([92.]); o=np.asarray([97.])
    interval=np.empty(1); hit_h=np.empty(1); hit_l=np.empty(1)
    geometric_interval_probability(l,h,p1,p2,interval)
    first_passage_probability(o,h,l,hit_h,hit_l)
    np.testing.assert_array_equal(interval,[.2])
    np.testing.assert_array_equal(hit_h,[.7])
    np.testing.assert_array_equal(hit_l,[.3])

def test_empirical_edge():
    empirical=np.asarray([.8]); geometric=np.asarray([.7]); n=np.asarray([100.])
    out=np.empty((1,5),dtype=np.float64)
    empirical_edge(empirical,geometric,n,out)
    np.testing.assert_allclose(out[0], [.8,.7,.1,2.1821789023599236,.0291363370103729], rtol=0, atol=1e-12)

def test_noncontiguous_input_is_rejected_instead_of_copied():
    o=np.zeros(8,dtype=np.float64)[::2]
    h=np.ones(4,dtype=np.float64)
    l=np.zeros(4,dtype=np.float64)
    c=np.zeros(4,dtype=np.float64)
    out=np.empty((4,5),dtype=np.float64)
    with pytest.raises(TypeError):
        candle_geometry(o,h,l,c,out)
