"""
Probability & Statistics Engine — pure statistical computation.

Research-only. No ML. All random processes are seeded and reproducible.
"""

from researchos.engines.quant.probability.bayesian import (
    BetaPosterior,
    HiddenMarkovModel,
    MarkovChain,
    estimate_markov_chain,
)
from researchos.engines.quant.probability.contracts import (
    ConfidenceInterval,
    DistributionFit,
    DistributionType,
    HypothesisTestResult,
    MonteCarloResult,
    TestStatistic,
)
from researchos.quant_engine.probability.mle import (
    generic_grid_mle,
    mle_log_normal,
    mle_normal,
    mle_student_t,
)
from researchos.engines.quant.probability.statistics import (
    bootstrap_mean,
    confidence_interval_mean,
    empirical_cdf,
    fit_log_normal,
    fit_normal,
    fit_student_t,
    kernel_density_estimate,
    log_normal_pdf,
    monte_carlo_normal,
    monte_carlo_return_paths,
    normal_cdf,
    normal_pdf,
    one_sample_t_test,
    probability_calibration,
    student_t_cdf,
    student_t_pdf,
    z_test,
)

__all__ = [
    "ConfidenceInterval",
    "DistributionFit",
    "DistributionType",
    "HypothesisTestResult",
    "MonteCarloResult",
    "TestStatistic",
    "normal_pdf",
    "normal_cdf",
    "student_t_pdf",
    "student_t_cdf",
    "log_normal_pdf",
    "empirical_cdf",
    "fit_normal",
    "fit_log_normal",
    "fit_student_t",
    "kernel_density_estimate",
    "confidence_interval_mean",
    "one_sample_t_test",
    "z_test",
    "bootstrap_mean",
    "monte_carlo_normal",
    "monte_carlo_return_paths",
    "probability_calibration",
    "BetaPosterior",
    "MarkovChain",
    "HiddenMarkovModel",
    "estimate_markov_chain",
    "mle_normal",
    "mle_log_normal",
    "mle_student_t",
    "generic_grid_mle",
]
