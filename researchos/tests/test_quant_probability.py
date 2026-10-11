"""
Unit tests for the Probability & Statistics Engine (WP-4 direct coverage).

Phase 5.1 — Certified Analytical Compute Surface (WP-4).
These tests observe the existing deterministic behavior of the probability
submodule. Pure research-only tests; no trading logic.

Covers:
    - Distribution fitting (normal, log-normal, student-t, kde)
    - Confidence intervals
    - Hypothesis tests (one-sample t, z)
    - Bootstrap / Monte Carlo (seeded determinism)
    - Probability calibration
    - Determinism on identical inputs
    - Edge cases / input validation errors
"""

import pytest

from researchos.quant_engine.probability.statistics import (
    bootstrap_mean,
    confidence_interval_mean,
    empirical_cdf,
    fit_log_normal,
    fit_normal,
    fit_student_t,
    kernel_density_estimate,
    monte_carlo_normal,
    monte_carlo_return_paths,
    normal_cdf,
    normal_pdf,
    one_sample_t_test,
    probability_calibration,
    student_t_cdf,
    z_test,
)


def _returns(length: int = 60) -> list:
    return [0.01 if i % 2 == 0 else -0.008 for i in range(length)]


class TestDistributionFitting:
    def test_fit_normal_structure(self):
        samples = _returns(50)
        fit = fit_normal(samples)
        assert fit.sample_size == 50
        assert "mean" in fit.parameters
        assert "std" in fit.parameters
        assert fit.parameters["std"] >= 0.0

    def test_fit_normal_mean_does_not_overflow_for_large_finite_samples(self):
        fit = fit_normal([1e308, 1e308, 1e308])
        assert fit.parameters["mean"] == pytest.approx(1e308)
        assert fit.parameters["std"] == 0.0

    def test_fit_normal_mean(self):
        samples = [1.0, 2.0, 3.0, 4.0, 5.0]
        fit = fit_normal(samples)
        assert abs(fit.parameters["mean"] - 3.0) < 1e-12

    def test_fit_normal_empty_raises(self):
        with pytest.raises(ValueError):
            fit_normal([])

    def test_fit_log_normal(self):
        samples = [1.0, 2.0, 4.0, 8.0]
        fit = fit_log_normal(samples)
        assert "mu" in fit.parameters
        assert "sigma" in fit.parameters
        assert fit.sample_size == 4

    def test_fit_log_normal_rejects_non_positive(self):
        with pytest.raises(ValueError):
            fit_log_normal([1.0, -1.0])

    def test_fit_student_t(self):
        samples = _returns(40)
        fit = fit_student_t(samples, df=5.0)
        assert "df" in fit.parameters
        assert fit.parameters["df"] == 5.0
        assert "loc" in fit.parameters
        assert "scale" in fit.parameters

    def test_kernel_density_estimate_determinism(self):
        samples = [1.0, 2.0, 3.0, 4.0, 5.0]
        k1 = kernel_density_estimate(samples, 2.5)
        k2 = kernel_density_estimate(samples, 2.5)
        assert k1 == k2
        assert 0.0 < k1 < 1.0

    def test_kernel_density_empty_raises(self):
        with pytest.raises(ValueError):
            kernel_density_estimate([], 1.0)


class TestDeterminism:
    def test_fit_normal_deterministic(self):
        samples = _returns(50)
        f1 = fit_normal(samples)
        f2 = fit_normal(samples)
        assert f1.parameters == f2.parameters
        assert f1.log_likelihood == f2.log_likelihood

    def test_monte_carlo_seeded_determinism(self):
        m1 = monte_carlo_normal(num_samples=1000, seed=42)
        m2 = monte_carlo_normal(num_samples=1000, seed=42)
        assert m1.samples == m2.samples
        assert m1.mean == m2.mean

    def test_bootstrap_seeded_determinism(self):
        samples = _returns(30)
        b1 = bootstrap_mean(samples, num_resamples=100, seed=7)
        b2 = bootstrap_mean(samples, num_resamples=100, seed=7)
        assert b1.mean == b2.mean
        assert b1.samples == b2.samples


class TestConfidenceInterval:
    def test_confidence_interval_mean(self):
        samples = _returns(60)
        ci = confidence_interval_mean(samples, confidence_level=0.95)
        assert ci.lower <= ci.upper
        assert ci.confidence_level == 0.95
        assert ci.method == "normal_approximation"

    def test_confidence_interval_needs_two(self):
        with pytest.raises(ValueError):
            confidence_interval_mean([1.0])


class TestHypothesisTests:
    def test_one_sample_t_test(self):
        samples = _returns(40)
        result = one_sample_t_test(samples, mu0=0.0, significance_level=0.05)
        assert result.test_name == "one_sample_t"
        assert 0.0 <= result.p_value <= 1.0
        assert result.significance_level == 0.05

    def test_one_sample_t_deterministic(self):
        samples = _returns(40)
        r1 = one_sample_t_test(samples)
        r2 = one_sample_t_test(samples)
        assert r1.statistic == r2.statistic
        assert r1.p_value == r2.p_value

    def test_z_test(self):
        result = z_test(
            sample_mean=0.01,
            population_mean=0.0,
            std_dev=0.02,
            n=100,
            significance_level=0.05,
        )
        assert result.test_name == "z_test"
        assert 0.0 <= result.p_value <= 1.0

    def test_z_test_invalid_std(self):
        with pytest.raises(ValueError):
            z_test(0.01, 0.0, -1.0, 100)

    def test_z_test_invalid_n(self):
        with pytest.raises(ValueError):
            z_test(0.01, 0.0, 0.02, 0)


class TestCalibration:
    def test_probability_calibration(self):
        predicted = [0.1, 0.4, 0.6, 0.9, 0.5, 0.3, 0.8, 0.2, 0.7, 0.4]
        actual = [0, 0, 1, 1, 1, 0, 1, 0, 1, 0]
        out = probability_calibration(predicted, actual, num_bins=10)
        assert len(out["bin_labels"]) == len(out["predicted_probabilities"])
        assert len(out["predicted_probabilities"]) == len(out["observed_frequencies"])

    def test_probability_calibration_mismatch(self):
        with pytest.raises(ValueError):
            probability_calibration([0.1, 0.2], [0, 0, 0])


class TestCDFPDF:
    def test_normal_pdf_positive(self):
        assert normal_pdf(0.0) > 0.0

    def test_normal_pdf_invalid_sigma(self):
        with pytest.raises(ValueError):
            normal_pdf(0.0, sigma=0.0)

    def test_normal_cdf_bounds(self):
        assert 0.0 <= normal_cdf(0.0) <= 1.0
        assert abs(normal_cdf(0.0) - 0.5) < 1e-12

    def test_student_t_cdf(self):
        assert 0.0 <= student_t_cdf(0.0, df=5.0) <= 1.0

    def test_empirical_cdf(self):
        samples = [1.0, 2.0, 3.0, 4.0]
        assert empirical_cdf(samples, 2.5) == 0.5

    def test_empirical_cdf_empty(self):
        with pytest.raises(ValueError):
            empirical_cdf([], 1.0)


class TestMonteCarlo:
    def test_monte_carlo_return_paths(self):
        result = monte_carlo_return_paths(
            initial_value=100.0,
            mu=0.0,
            sigma=0.01,
            periods=10,
            num_paths=20,
            seed=42,
        )
        assert result.num_samples == 20
        assert result.mean is not None
        assert result.std >= 0.0

    def test_monte_carlo_return_paths_deterministic(self):
        r1 = monte_carlo_return_paths(100.0, 0.0, 0.01, 10, 20, seed=1)
        r2 = monte_carlo_return_paths(100.0, 0.0, 0.01, 10, 20, seed=1)
        assert r1.samples == r2.samples
