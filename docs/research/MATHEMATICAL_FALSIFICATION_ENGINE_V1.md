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

The current Monte Carlo implementation reports aggregate terminal-price moments and quantiles. `audit_monte_carlo_summary` therefore rejects malformed summaries but returns `INCONCLUSIVE` for a merely coherent summary. The stronger `audit_monte_carlo_replay` independently reruns the current empirical-resampling algorithm from the exact input prices, simulation count, and seed, then compares all reported moments and quantiles within a declared tolerance.

A reproducible replay requires an immutable artifact containing:
- exact input series and its hash;
- algorithm/version and source commit SHA;
- RNG family, seed, simulation count, horizon, and resampling/model assumptions;
- raw paths or sufficient replay inputs;
- independently recomputed moments and quantiles;
- convergence/error diagnostics across predeclared simulation budgets;
- model checks against observed out-of-sample outcomes.

A successful replay establishes numerical reproducibility of the declared algorithm only. It does not prove that iid resampling is a valid market model or that future prices follow the simulated distribution.

## Falsification is not the same as failed verification

A calculation can be arithmetically correct while its assumptions are false. Conversely, an inability to verify a claim is not proof that the claim is false. QROS must preserve these separate states rather than collapsing all non-passes into a single verdict.

## Next integration boundary

The v1 functions are pure audit primitives with unit tests. They are not yet wired into every Bayesian, Monte Carlo, GBM, calibration, or strategy decision path. Production integration must collect source evidence and call independent checks at the point where model outputs become research claims. No market profitability claim is established by these unit tests.
