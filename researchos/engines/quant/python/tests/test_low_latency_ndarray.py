import numpy as np
import pytest


try:
    from cpp_quant_engine.cpp_quant_backend import (
        bayesian_filter_binary,
        gbm_terminal_from_shocks,
        candle_geometry,
        geometric_interval_probability,
        first_passage_probability,
        empirical_edge,
        heat_density,
        heat_interval_probability,
        gbm_lognormal_density,
        ou_transition_moments,
        ou_interval_probability,
        market_velocity_momentum,
        market_force,
        shannon_entropy,
        shannon_normalized_entropy,
    )
except ImportError:
    bayesian_filter_binary = None
    gbm_terminal_from_shocks = None
    candle_geometry = None
    geometric_interval_probability = None
    first_passage_probability = None
    empirical_edge = None
    heat_density = None
    heat_interval_probability = None
    gbm_lognormal_density = None
    ou_transition_moments = None
    ou_interval_probability = None
    market_velocity_momentum = None
    market_force = None
    shannon_entropy = None
    shannon_normalized_entropy = None


pytestmark = pytest.mark.skipif(
    bayesian_filter_binary is None
    or gbm_terminal_from_shocks is None
    or candle_geometry is None
    or geometric_interval_probability is None
    or first_passage_probability is None
    or empirical_edge is None
    or heat_density is None
    or heat_interval_probability is None
    or gbm_lognormal_density is None
    or ou_transition_moments is None
    or ou_interval_probability is None
    or market_velocity_momentum is None
    or market_force is None
    or shannon_entropy is None
    or shannon_normalized_entropy is None,
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


def test_candle_geometry_writes_caller_owned_array():
    o = np.asarray([97.0, 90.0])
    h = np.asarray([100.0, 100.0])
    low = np.asarray([90.0, 80.0])
    c = np.asarray([98.0, 85.0])
    out = np.empty((2, 5), dtype=np.float64)

    candle_geometry(o, h, low, c, out)

    np.testing.assert_allclose(
        out,
        [[10.0, 0.1, 0.2, 0.7, 0.8], [20.0, 0.25, 0.25, 0.25, 0.25]],
        rtol=0.0,
        atol=0.0,
    )


def test_geometric_null_and_first_passage():
    low = np.asarray([90.0])
    high = np.asarray([100.0])
    p1 = np.asarray([90.0])
    p2 = np.asarray([92.0])
    open_ = np.asarray([97.0])
    interval = np.empty(1, dtype=np.float64)
    hit_high = np.empty(1, dtype=np.float64)
    hit_low = np.empty(1, dtype=np.float64)

    geometric_interval_probability(low, high, p1, p2, interval)
    first_passage_probability(open_, high, low, hit_high, hit_low)

    np.testing.assert_array_equal(interval, [0.2])
    np.testing.assert_array_equal(hit_high, [0.7])
    np.testing.assert_array_equal(hit_low, [0.3])


def test_empirical_edge():
    empirical = np.asarray([0.8])
    geometric = np.asarray([0.7])
    sample_size = np.asarray([100.0])
    out = np.empty((1, 5), dtype=np.float64)

    empirical_edge(empirical, geometric, sample_size, out)

    np.testing.assert_allclose(
        out[0],
        [0.8, 0.7, 0.1, 2.1821789023599236, 0.0291363370103729],
        rtol=0.0,
        atol=1e-12,
    )



def test_diffusion_heat_kernel_and_gbm_density():
    x = np.asarray([0.0, 1.0])
    mean = np.asarray([0.0, 0.0])
    diffusion = np.asarray([0.5, 0.5])
    time = np.asarray([1.0, 1.0])
    density = np.empty(2, dtype=np.float64)
    heat_density(x, mean, diffusion, time, density)
    np.testing.assert_allclose(
        density,
        [1.0 / np.sqrt(2.0 * np.pi), np.exp(-0.5) / np.sqrt(2.0 * np.pi)],
        rtol=0.0,
        atol=1e-14,
    )

    lower = np.asarray([-1.0])
    upper = np.asarray([1.0])
    interval = np.empty(1, dtype=np.float64)
    heat_interval_probability(
        np.asarray([0.0]), np.asarray([0.5]), np.asarray([1.0]),
        lower, upper, interval
    )
    np.testing.assert_allclose(interval, [0.682689492137086], rtol=0.0, atol=1e-14)

    gbm = np.empty(1, dtype=np.float64)
    gbm_lognormal_density(
        np.asarray([100.0]), np.asarray([100.0]), np.asarray([0.05]),
        np.asarray([0.2]), np.asarray([1.0]), gbm
    )
    assert np.isfinite(gbm[0]) and gbm[0] > 0.0


def test_ornstein_uhlenbeck_mean_reversion():
    x0 = np.asarray([110.0])
    theta = np.asarray([1.0])
    mu = np.asarray([100.0])
    sigma = np.asarray([2.0])
    time = np.asarray([1.0])
    moments = np.empty((1, 2), dtype=np.float64)
    ou_transition_moments(x0, theta, mu, sigma, time, moments)

    expected_mean = 100.0 + 10.0 * np.exp(-1.0)
    expected_variance = 4.0 * (1.0 - np.exp(-2.0)) / 2.0
    np.testing.assert_allclose(
        moments[0], [expected_mean, expected_variance], rtol=0.0, atol=1e-14
    )

    probability = np.empty(1, dtype=np.float64)
    ou_interval_probability(
        x0, theta, mu, sigma, time,
        np.asarray([100.0]), np.asarray([105.0]), probability
    )
    assert 0.0 < probability[0] < 1.0


def test_market_momentum_and_force():
    out = np.empty((2, 2), dtype=np.float64)
    market_velocity_momentum(
        np.asarray([2.0, -1.0]),
        np.asarray([10.0, 20.0]),
        np.asarray([1.0, 0.5]),
        out,
    )
    np.testing.assert_allclose(out, [[2.0, 20.0], [-2.0, -40.0]], rtol=0.0, atol=0.0)

    force = np.empty(2, dtype=np.float64)
    market_force(
        np.asarray([20.0, -40.0]),
        np.asarray([10.0, -20.0]),
        np.asarray([2.0, 2.0]),
        force,
    )
    np.testing.assert_array_equal(force, [5.0, -10.0])


def test_shannon_entropy_and_normalized_entropy():
    probabilities = np.asarray([[0.5, 0.5], [1.0, 0.0]], dtype=np.float64)
    entropy = np.empty(2, dtype=np.float64)
    normalized = np.empty(2, dtype=np.float64)
    shannon_entropy(probabilities, entropy)
    shannon_normalized_entropy(probabilities, normalized)
    np.testing.assert_allclose(
        entropy, [np.log(2.0), 0.0], rtol=0.0, atol=1e-14
    )
    np.testing.assert_allclose(
        normalized, [1.0, 0.0], rtol=0.0, atol=1e-14
    )


def test_noncontiguous_input_is_rejected_instead_of_copied():
    shocks = np.zeros((4, 4), dtype=np.float64)[::2]
    out = np.empty(2, dtype=np.float64)
    with pytest.raises(TypeError):
        gbm_terminal_from_shocks(shocks, 100.0, 0.05, 0.20, 1.0, out)

    open_ = np.zeros(8, dtype=np.float64)[::2]
    high = np.ones(4, dtype=np.float64)
    low = np.zeros(4, dtype=np.float64)
    close = np.zeros(4, dtype=np.float64)
    geometry_out = np.empty((4, 5), dtype=np.float64)
    with pytest.raises(TypeError):
        candle_geometry(open_, high, low, close, geometry_out)
