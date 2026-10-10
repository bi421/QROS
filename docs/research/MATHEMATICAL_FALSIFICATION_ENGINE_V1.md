# Mathematical Falsification Engine v1

## Purpose

QROS already computes Bayesian summaries and Monte Carlo terminal-distribution summaries. Those outputs are not self-authenticating. This module adds an independent audit boundary that asks whether reported mathematical claims are consistent with their declared equations and evidence.

It deliberately distinguishes four outcomes:

- `VERIFIED`: the checked identity matches within a declared numerical tolerance.
- `FALSIFIED`: the reported value contradicts the checked mathematical identity or contract.
- `INCONCLUSIVE`: the available summary is insufficient to verify the claim.
- `INVALID_INPUT`: the evidence contract is malformed or violates input constraints.

## Bayesian identity

For a Beta prior and Bernoulli observations:

```text
alpha_post = alpha_prior + successes
beta_post  = beta_prior + failures
posterior_mean = alpha_post / (alpha_post + beta_post)
```

The audit recomputes these values independently from the reported measurement and compares them with the declared tolerance. A mismatch falsifies the *reported calculation*, not necessarily the underlying trading hypothesis. Even a verified posterior does not validate the prior, conditional independence/exchangeability, event definition, or data integrity.

## Monte Carlo boundary

The current Monte Carlo implementation reports aggregate terminal-price moments and quantiles, but does not expose the raw paths as an evidence artifact. Therefore `audit_monte_carlo_summary` only rejects malformed or internally impossible summaries and otherwise returns `INCONCLUSIVE`. It does not claim to verify the random-number stream, simulation paths, sampling assumptions, convergence, or market realism.

A stronger Monte Carlo audit requires an immutable artifact containing:
- exact input series and its hash;
- algorithm/version and source commit SHA;
- RNG family, seed, simulation count, horizon, and resampling/model assumptions;
- raw paths or sufficient replay inputs;
- independently recomputed moments and quantiles;
- convergence/error diagnostics across predeclared simulation budgets;
- model checks against observed out-of-sample outcomes.

## Falsification is not the same as failed verification

A calculation can be arithmetically correct while its assumptions are false. Conversely, an inability to verify a claim is not proof that the claim is false. QROS must preserve these separate states rather than collapsing all non-passes into a single verdict.

## Next integration boundary

The v1 functions are pure audit primitives with unit tests. They are not yet wired into every Bayesian, Monte Carlo, GBM, calibration, or strategy decision path. Production integration must collect source evidence and call independent checks at the point where model outputs become research claims. No market profitability claim is established by these unit tests.
