import numpy as np
import pytest


try:
    from cpp_quant_engine.cpp_quant_backend import (
        bayesian_filter_binary,
        gbm_terminal_from_shocks,
    )
except ImportError:
    bayesian_filter_binary = None
    gbm_terminal_from_shocks = None


pytestmark = pytest.mark.skipif(
    bayesian_filter_binary is None or gbm_terminal_from_shocks is None,
    reason="compiled nanobind Quant Engine is unavailable",
)


def test_bayesian_filter_writes_into_caller_owned_array():
    signal = np.asarray([1.0, 0.0, 1.0], dtype=np.float64)
    p_up = np.asarray([0.70, 0.20, 0.80], dtype=np.float64)
    p_down = np.asarray([0.30, 0.60, 0.40], dtype=np.float64)
    out = np.empty(3, dtype=np.float64)

    bayesian_filter_binary(signal, p_up, p_down, 0.50, out)

    expected = []
    posterior = 0.50
    for s, up, down in zip(signal, p_up, p_down):
        lu = up if s == 1.0 else 1.0 - up
        ld = down if s == 1.0 else 1.0 - down
        posterior = posterior * lu / (posterior * lu + (1.0 - posterior) * ld)
        expected.append(posterior)

    np.testing.assert_allclose(out, expected, rtol=0.0, atol=1e-14)


def test_gbm_terminal_is_zero_copy_and_deterministic():
    shocks = np.zeros((2, 4), dtype=np.float64)
    out = np.full(2, -1.0, dtype=np.float64)

    gbm_terminal_from_shocks(shocks, 100.0, 0.05, 0.20, 1.0, out)

    expected = 100.0 * np.exp(0.05 - 0.5 * 0.20 * 0.20)
    np.testing.assert_array_equal(out, np.asarray([expected, expected]))


def test_noncontiguous_input_is_rejected_instead_of_copied():
    shocks = np.zeros((4, 4), dtype=np.float64)[::2]
    out = np.empty(2, dtype=np.float64)

    with pytest.raises(TypeError):
        gbm_terminal_from_shocks(shocks, 100.0, 0.05, 0.20, 1.0, out)
