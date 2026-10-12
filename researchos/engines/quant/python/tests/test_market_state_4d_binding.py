import numpy as np
import pytest
native = pytest.importorskip("qros_market_state_4d")

def test_dual_clock_latency_binding_borrows_inputs_and_derives_ms():
    event=np.array([1_800_000_000_000_000_000],dtype=np.int64)
    ingest=np.array([1_800_000_000_005_000_000],dtype=np.int64)
    out=native.derive_latency_ms(np.array([2300.0]),np.array([1.0]),event,ingest)
    assert out.tolist()==[5.0]

def test_binding_rejects_mismatched_arrays_and_bad_price():
    with pytest.raises(ValueError,match="equal length"):
        native.derive_latency_ms(np.array([2300.0]),np.array([],dtype=float),
                                 np.array([100],dtype=np.int64),np.array([101],dtype=np.int64),1.0)
    with pytest.raises(ValueError,match="price"):
        native.derive_latency_ms(np.array([0.0]),np.array([1.0]),
                                 np.array([100],dtype=np.int64),np.array([101],dtype=np.int64),1.0)
