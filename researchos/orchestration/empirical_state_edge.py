"""Empirical candle-state continuation probabilities and chi-square diagnostics.

States are fixed, causal bins. Wilson intervals describe binomial uncertainty;
exact binomial tests assess a predeclared null rate. Chi-square GOF is used only
for sufficiently populated categorical bins and does not establish profitability.
"""

from __future__ import annotations
import math
from collections import defaultdict
from typing import Iterable, Mapping, Sequence

from researchos.orchestration.binomial_edge import binomial_edge_test
from researchos.orchestration.statistical_validation import benjamini_hochberg


def empirical_state_probability(
    successes: int, trials: int, *, confidence: float = 0.95
) -> dict[str, float | int]:
    """Return p_hat, Wilson interval, and counts for a pre-defined state."""
    if isinstance(trials, bool) or not isinstance(trials, int) or trials < 1:
        raise ValueError("trials must be an integer >= 1")
    if (
        isinstance(successes, bool)
        or not isinstance(successes, int)
        or not 0 <= successes <= trials
    ):
        raise ValueError("successes must be an integer in [0, trials]")
    result = binomial_edge_test(
        successes, trials, null_probability=0.5, alternative="two-sided", confidence=confidence
    )
    return {
        "successes": successes,
        "trials": trials,
        "probability": successes / trials,
        "wilson_lower": result["wilson_interval_lower"],
        "wilson_upper": result["wilson_interval_upper"],
    }


def chi_square_goodness_of_fit(
    observed: Sequence[int], expected_probabilities: Sequence[float], *, min_expected: float = 5.0
) -> dict[str, object]:
    """Pearson chi-square GOF with df=k-1; survival probability via regularized gamma.

    Requires pre-specified categories and expected probabilities summing to 1.
    Returns NOT_TESTABLE if expected cell counts are too small.
    """
    if len(observed) < 2 or len(observed) != len(expected_probabilities):
        raise ValueError("observed and expected_probabilities must have equal length >= 2")
    if any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in observed):
        raise ValueError("observed counts must be nonnegative integers")
    probs = [float(p) for p in expected_probabilities]
    if any(not math.isfinite(p) or p <= 0 or p >= 1 for p in probs) or abs(sum(probs) - 1.0) > 1e-9:
        raise ValueError("expected probabilities must be in (0,1) and sum to 1")
    if not math.isfinite(min_expected) or min_expected <= 0:
        raise ValueError("min_expected must be positive")
    n = sum(observed)
    if n < 1:
        raise ValueError("at least one observation is required")
    expected = [n * p for p in probs]
    if min(expected) < min_expected:
        return {
            "status": "NOT_TESTABLE_EXPECTED_COUNTS_TOO_SMALL",
            "n": n,
            "observed": list(observed),
            "expected": expected,
            "chi_square": None,
            "degrees_freedom": len(observed) - 1,
            "p_value": None,
            "reject_at_0_05": False,
        }
    statistic = math.fsum((o - e) ** 2 / e for o, e in zip(observed, expected))
    df = len(observed) - 1
    pvalue = _regularized_gamma_q(df / 2.0, statistic / 2.0)
    return {
        "status": "TESTED",
        "n": n,
        "observed": list(observed),
        "expected": expected,
        "chi_square": statistic,
        "degrees_freedom": df,
        "p_value": pvalue,
        "reject_at_0_05": pvalue < 0.05,
    }


def _regularized_gamma_q(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a,x), Numerical Recipes algorithms."""
    if x < 0 or a <= 0:
        raise ValueError("a must be positive and x nonnegative")
    if x == 0:
        return 1.0
    gln = math.lgamma(a)
    eps = 3e-14
    tiny = 1e-300
    max_iter = 10000
    if x < a + 1.0:
        ap = a
        term = 1.0 / a
        total = term
        for _ in range(max_iter):
            ap += 1
            term *= x / ap
            total += term
            if abs(term) < abs(total) * eps:
                break
        p = total * math.exp(-x + a * math.log(x) - gln)
        return min(1.0, max(0.0, 1.0 - p))
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, max_iter + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return min(1.0, max(0.0, math.exp(-x + a * math.log(x) - gln) * h))


def evaluate_state_table(
    rows: Iterable[Mapping[str, object]],
    *,
    state_fields: Sequence[str],
    outcome_field: str,
    null_probability: float = 0.5,
    min_trials: int = 30,
    fdr_q: float = 0.05,
) -> dict[str, object]:
    """Group records by fixed state fields; BH-adjust state-wise exact binomial tests.

    Outcome must be bool/0/1. Caller must ensure rows are chronological, causal,
    and labels do not leak future information into state features.
    """
    if not state_fields or min_trials < 1:
        raise ValueError("state_fields required and min_trials >= 1")
    grouped = defaultdict(list)
    for row in rows:
        if any(k not in row for k in (*state_fields, outcome_field)):
            raise ValueError("missing state/outcome field")
        outcome = row[outcome_field]
        if outcome not in (True, False, 0, 1):
            raise ValueError("outcome must be boolean or 0/1")
        grouped[tuple(row[k] for k in state_fields)].append(int(outcome))
    results = []
    for state, labels in grouped.items():
        n = len(labels)
        wins = sum(labels)
        entry = {"state": dict(zip(state_fields, state)), **empirical_state_probability(wins, n)}
        if n >= min_trials:
            test = binomial_edge_test(
                wins, n, null_probability=null_probability, alternative="greater"
            )
            entry.update(
                {
                    "test_status": "TESTED",
                    "null_probability": null_probability,
                    "p_value": test["exact_p_value"],
                    "reject_null_uncorrected": test["reject_null_at_0_05"],
                }
            )
        else:
            entry.update(
                {
                    "test_status": "INSUFFICIENT_SAMPLE",
                    "null_probability": null_probability,
                    "p_value": None,
                    "reject_null_uncorrected": False,
                }
            )
        results.append(entry)
    eligible = [(i, r["p_value"]) for i, r in enumerate(results) if r["p_value"] is not None]
    adjusted = benjamini_hochberg([p for _, p in eligible], q=fdr_q)
    for (i, _), adj in zip(eligible, adjusted):
        results[i]["p_adjusted_bh"] = adj["p_adjusted_bh"]
        results[i]["reject_after_fdr"] = adj["reject_at_q"]
    return {
        "states": results,
        "state_count": len(results),
        "tested_states": len(eligible),
        "fdr_q": fdr_q,
        "warning": "Statistical significance is not proof of net profitability; serial dependence, overlapping labels, bin selection and multiple testing must be controlled.",
    }


__all__ = ["empirical_state_probability", "chi_square_goodness_of_fit", "evaluate_state_table"]
