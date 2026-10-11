"""
Probability & Statistics Engine — distributions and estimators.

Deterministic statistical computation using a seeded RNG. All public
functions accept an explicit ``seed`` parameter and are reproducible.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

from researchos.quant_engine.probability.contracts import (
    ConfidenceInterval,
    DistributionFit,
    DistributionType,
    HypothesisTestResult,
    MonteCarloResult,
)

# ──────────────────────────────────────────────
# Distribution PDF/CDF helpers
# ──────────────────────────────────────────────


def normal_pdf(x: float, mu: float = 0.0, sigma: float = 1.0) -> float:
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    return math.exp(-0.5 * ((x - mu) / sigma) ** 2) / (sigma * math.sqrt(2.0 * math.pi))


def normal_cdf(x: float, mu: float = 0.0, sigma: float = 1.0) -> float:
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    return 0.5 * (1.0 + math.erf((x - mu) / (sigma * math.sqrt(2.0))))


def _t_pdf(x: float, df: float) -> float:
    if df <= 0:
        raise ValueError("df must be positive")
    return math.gamma((df + 1.0) / 2.0) / (math.sqrt(df * math.pi) * math.gamma(df / 2.0)) * (1.0 + (x * x) / df) ** (-(df + 1.0) / 2.0)


def student_t_pdf(x: float, df: float) -> float:
    return _t_pdf(x, df)


def student_t_cdf(x: float, df: float) -> float:
    """Approximate Student-t CDF via numerical integration (Simpson)."""
    if df <= 0:
        raise ValueError("df must be positive")
    steps = 2000
    a = -10.0
    if x < a:
        return 0.0
    if x > 10.0:
        return 1.0
    width = (x - a) / steps
    total = 0.0
    for i in range(steps + 1):
        t = a + i * width
        w = 1.0
        if 0 < i < steps:
            w = 2.0 if i % 2 == 0 else 4.0
        total += w * _t_pdf(t, df)
    return total * width / 3.0


def log_normal_pdf(x: float, mu: float = 0.0, sigma: float = 1.0) -> float:
    if sigma <= 0 or x <= 0:
        return 0.0 if x <= 0 else 0.0
    if x <= 0:
        return 0.0
    return math.exp(-0.5 * ((math.log(x) - mu) / sigma) ** 2) / (x * sigma * math.sqrt(2.0 * math.pi))


def empirical_cdf(samples: Sequence[float], x: float) -> float:
    if len(samples) == 0:
        raise ValueError("samples must be non-empty")
    count = sum(1.0 for s in samples if s <= x)
    return count / len(samples)


# ──────────────────────────────────────────────
# Distribution fitting
# ──────────────────────────────────────────────


def fit_normal(samples: Sequence[float]) -> DistributionFit:
    n = len(samples)
    if n == 0:
        raise ValueError("samples must be non-empty")
    mean = sum(samples) / n
    var = sum((s - mean) ** 2 for s in samples) / n
    return DistributionFit(
        distribution=DistributionType.NORMAL,
        parameters={"mean": mean, "std": math.sqrt(var)},
        log_likelihood=-0.5 * n * math.log(2.0 * math.pi * var) - n / 2.0,
        sample_size=n,
    )


def fit_log_normal(samples: Sequence[float]) -> DistributionFit:
    n = len(samples)
    if n == 0:
        raise ValueError("samples must be non-empty")
    if any(s <= 0 for s in samples):
        raise ValueError("log-normal fit requires strictly positive samples")
    logs = [math.log(s) for s in samples]
    mean = sum(logs) / n
    var = sum((lg - mean) ** 2 for lg in logs) / n
    return DistributionFit(
        distribution=DistributionType.LOG_NORMAL,
        parameters={"mu": mean, "sigma": math.sqrt(var)},
        log_likelihood=-0.5 * n * math.log(2.0 * math.pi * var) - sum(logs) - n / 2.0,
        sample_size=n,
    )


def fit_student_t(samples: Sequence[float], df: float = 5.0) -> DistributionFit:
    n = len(samples)
    if n == 0:
        raise ValueError("samples must be non-empty")
    mean = sum(samples) / n
    var = sum((s - mean) ** 2 for s in samples) / n
    scale = math.sqrt(var * (df - 2.0) / df) if df > 2 else math.sqrt(var)
    ll = sum(math.log(_t_pdf((s - mean) / scale, df)) for s in samples)
    return DistributionFit(
        distribution=DistributionType.STUDENT_T,
        parameters={"df": float(df), "loc": mean, "scale": scale},
        log_likelihood=ll,
        sample_size=n,
    )


def kernel_density_estimate(
    samples: Sequence[float],
    x: float,
    bandwidth: float | None = None,
) -> float:
    n = len(samples)
    if n == 0:
        raise ValueError("samples must be non-empty")
    if bandwidth is None:
        sd = _std(samples)
        bandwidth = 1.06 * sd * (n**-0.2)
    if bandwidth <= 0:
        bandwidth = 1e-8
    return sum(normal_pdf(x, s, bandwidth) for s in samples) / n


def _mean(samples: Sequence[float]) -> float:
    if not samples:
        raise ValueError("samples must be non-empty")
    return math.fsum(sample / len(samples) for sample in samples)


def _std(samples: Sequence[float]) -> float:
    m = _mean(samples)
    return math.sqrt(sum((s - m) ** 2 for s in samples) / len(samples))


# ──────────────────────────────────────────────
# Confidence intervals & hypothesis tests
# ──────────────────────────────────────────────


def confidence_interval_mean(
    samples: Sequence[float],
    confidence_level: float = 0.95,
) -> ConfidenceInterval:
    n = len(samples)
    if n < 2:
        raise ValueError("need at least 2 samples")
    mean = _mean(samples)
    sd = _std(samples)
    se = sd / math.sqrt(n)
    # Normal approximation z-score
    z = _normal_ppf(0.5 + confidence_level / 2.0)
    return ConfidenceInterval(
        lower=mean - z * se,
        upper=mean + z * se,
        confidence_level=confidence_level,
        method="normal_approximation",
    )


def _normal_ppf(p: float) -> float:
    """Inverse normal CDF (Acklam's approximation)."""
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]

    if p <= 0:
        return -float("inf")
    if p >= 1:
        return float("inf")

    if p < 0.02425:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    if p > 0.97575:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)

    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)


def one_sample_t_test(
    samples: Sequence[float],
    mu0: float = 0.0,
    significance_level: float = 0.05,
) -> HypothesisTestResult:
    n = len(samples)
    if n < 2:
        raise ValueError("need at least 2 samples")
    mean = _mean(samples)
    sd = _std(samples)
    se = sd / math.sqrt(n)
    if se == 0:
        raise ValueError("zero variance sample")
    t_stat = (mean - mu0) / se
    df = n - 1
    # Two-tailed approximate p-value via t → normal for large df (simplified).
    p = 2.0 * (1.0 - _student_t_cdf_approx(abs(t_stat), df))
    return HypothesisTestResult(
        statistic=t_stat,
        p_value=max(0.0, min(1.0, p)),
        null_hypothesis=f"population mean = {mu0}",
        alternative_hypothesis=f"population mean != {mu0}",
        significance_level=significance_level,
        test_name="one_sample_t",
    )


def _student_t_cdf_approx(x: float, df: float) -> float:
    """Approximate Student-t CDF using normal approximation for df >= 30,
    otherwise a coarse numerical integration."""
    if df >= 30:
        return normal_cdf(x)
    return student_t_cdf(x, df)


def z_test(
    sample_mean: float,
    population_mean: float,
    std_dev: float,
    n: int,
    significance_level: float = 0.05,
) -> HypothesisTestResult:
    if n <= 0:
        raise ValueError("n must be positive")
    if std_dev <= 0:
        raise ValueError("std_dev must be positive")
    se = std_dev / math.sqrt(n)
    z = (sample_mean - population_mean) / se
    p = 2.0 * (1.0 - normal_cdf(abs(z)))
    return HypothesisTestResult(
        statistic=z,
        p_value=max(0.0, min(1.0, p)),
        null_hypothesis=f"population mean = {population_mean}",
        alternative_hypothesis=f"population mean != {population_mean}",
        significance_level=significance_level,
        test_name="z_test",
    )


# ──────────────────────────────────────────────
# Bootstrap & Monte Carlo
# ──────────────────────────────────────────────


def bootstrap_mean(
    samples: Sequence[float],
    num_resamples: int = 1000,
    seed: int = 42,
) -> MonteCarloResult:
    rng = random.Random(seed)
    n = len(samples)
    if n == 0:
        raise ValueError("samples must be non-empty")
    resample_means = []
    for _ in range(num_resamples):
        resample = [rng.choice(samples) for _ in range(n)]
        resample_means.append(sum(resample) / n)
    return _monte_carlo_result(resample_means, seed, num_resamples)


def monte_carlo_normal(
    num_samples: int = 10000,
    mu: float = 0.0,
    sigma: float = 1.0,
    seed: int = 42,
) -> MonteCarloResult:
    rng = random.Random(seed)
    samples = [rng.gauss(mu, sigma) for _ in range(num_samples)]
    return _monte_carlo_result(samples, seed, num_samples)


def monte_carlo_return_paths(
    initial_value: float,
    mu: float,
    sigma: float,
    periods: int = 252,
    num_paths: int = 1000,
    seed: int = 42,
) -> MonteCarloResult:
    rng = random.Random(seed)
    final_values = []
    for _ in range(num_paths):
        value = initial_value
        for _ in range(periods):
            value *= math.exp(rng.gauss(mu, sigma))
        final_values.append(value)
    return _monte_carlo_result(final_values, seed, num_paths)


def _monte_carlo_result(
    samples: list[float],
    seed: int,
    num_samples: int,
) -> MonteCarloResult:
    n = len(samples)
    mean = sum(samples) / n
    sd = _std(samples)
    percentiles = {}
    sorted_samples = sorted(samples)
    for p in (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99):
        idx = min(n - 1, max(0, int(p * n)))
        percentiles[p] = sorted_samples[idx]
    return MonteCarloResult(
        samples=samples,
        mean=mean,
        std=sd,
        percentiles=percentiles,
        seed=seed,
        num_samples=num_samples,
    )


def probability_calibration(
    predicted: Sequence[float],
    actual: Sequence[int],
    num_bins: int = 10,
) -> dict[str, float]:
    """Simple reliability/calibration table (research only)."""
    if len(predicted) != len(actual) or len(predicted) == 0:
        raise ValueError("predicted and actual must be equal-length, non-empty")
    bins: dict[int, dict[str, float]] = {}
    for p, a in zip(predicted, actual):
        idx = min(num_bins - 1, int(p * num_bins))
        bins.setdefault(idx, {"count": 0, "sum_pred": 0.0, "sum_actual": 0.0})
        bins[idx]["count"] += 1
        bins[idx]["sum_pred"] += p
        bins[idx]["sum_actual"] += a
    bin_labels = []
    bin_preds = []
    bin_actuals = []
    for idx in sorted(bins):
        b = bins[idx]
        bin_labels.append(idx)
        bin_preds.append(b["sum_pred"] / b["count"])
        bin_actuals.append(b["sum_actual"] / b["count"])
    return {
        "bin_labels": bin_labels,
        "predicted_probabilities": bin_preds,
        "observed_frequencies": bin_actuals,
    }
