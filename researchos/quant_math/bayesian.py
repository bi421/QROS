from __future__ import annotations

from researchos.quant_math.contracts import BayesianMeasurement


def beta_bernoulli(
    successes: int,
    failures: int,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
) -> BayesianMeasurement:
    if successes < 0 or failures < 0:
        raise ValueError("successes and failures must be non-negative")
    if prior_alpha <= 0 or prior_beta <= 0:
        raise ValueError("Beta prior parameters must be positive")
    a = prior_alpha + successes
    b = prior_beta + failures
    return BayesianMeasurement(
        prior_alpha,
        prior_beta,
        successes,
        failures,
        a,
        b,
        a / (a + b),
    )
