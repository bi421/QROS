# Hypothesis-driven edge research protocol

## Scope and safety

QROS research is offline and research-only; it never places orders. A statistically selected candidate is not a certified live edge. Missing or unverified broker costs must fail closed as `NO_TRADE`.

## Pre-registered hypotheses

The initial hypothesis catalogue is in `researchos/orchestration/hypothesis_research.py`. Each hypothesis has a written economic rationale and no more than three named parameters. These are testable ideas, not assertions that an edge exists.

## Costs

`config/costs.yaml` is JSON syntax, which is a valid YAML subset, so the initial reader needs no additional YAML dependency. Values are deliberately null and marked assumed. Fill the spread by session, round-trip commission/contract size, volatility-linked slippage, swap, and evidence metadata from the actual broker/account. Never set status to `VERIFIED` without auditable source evidence. A broker's published minimum spread alone is not a historical spread distribution.

## Trial registry and holdout

`scripts/qros_cli.py research run --hypothesis <id>` records a timestamped trial with hypothesis/data/config hashes and code SHA. The current command is **preflight-only**: it does not run strategy returns, walk-forward, negative controls, DSR/SPA, or cost sensitivity. It does not read the final 20% holdout. This limitation is printed in every CLI result.

The JSONL registry is hash-chained; `verify_trial_registry` checks each record hash, sequence number, and predecessor link, and new trials fail closed if the existing registry is inconsistent. This is tamper-evident, not tamper-proof storage. The one-time holdout lock uses exclusive file creation to prevent ordinary concurrent double claims, but remains a local guard, not a security boundary against manual file edits. Production enforcement requires a controlled CI job or append-only remote store and a frozen candidate artifact. Once holdout results are seen, that period must not be described as untouched again.

## Diagnostic stress tests

`run_five_overfitting_attacks` reports best-asset removal, chronological chunk stability, best-regime removal, top-five-trade removal, and seeded random-trade omission. These are concentration/stability diagnostics only; they do not preserve serial dependence in the random omission test and are not substitutes for block bootstrap, negative controls, or multiple-testing correction. Results never enable execution.

## Candidate gate

`evaluate_candidate_gate` applies predeclared minimum conditions: positive net expectancy and 95% CI lower bound, at least 70% positive walk-forward folds, positive net expectancy at 1.5x costs, multiplicity-adjusted significance, negative-control separation, no single year/regime contributing over 40%, verified costs, and a stable parameter plateau. Missing values fail closed. A CANDIDATE is eligible for one final holdout evaluation; it is not proof of business profitability.

## Not yet implemented

This is a safety/governance foundation, not the complete edge-discovery pipeline. The next implementation steps are:
1. Connect each hypothesis to a causal, independently tested signal generator and common cost-aware event simulator.
2. Add purged/embargoed rolling walk-forward net expectancy for each fold.
3. Add parameter-neighbour plateau tests, autocorrelation-preserving bootstrap, and cost sensitivity at 0.5x/1x/1.5x/2x.
4. Implement and independently test DSR plus White Reality Check or Hansen SPA across the complete registered trial family.
5. Add year/volatility/session regime breakdowns and random-entry, shuffled-signal, and shifted-signal negative controls.
6. Freeze eligible candidate hashes, then permit a single isolated final holdout run with a signed audit artifact.
7. Re-run the old 648 directional variants as exploratory diagnostics only; the previously inspected 19 positive gross intervals are not independent confirmation.
