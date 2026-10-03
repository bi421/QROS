# XAUUSD M1 frozen confirmation

## Purpose

Exploratory discovery may search many candidate conditions. That search result is not itself confirmation. This stage creates a chronological boundary:

`DEVELOPMENT → FREEZE CANDIDATE → UNTOUCHED CONFIRMATION`

The candidate definition and its probability estimate are fixed from development data before confirmation labels are evaluated.

## Default research split

The real XAUUSD M1 evidence set contains about 24.8k complete events. To preserve at least 10k events for an independent confirmation block, the first confirmation experiment should use a boundary that leaves roughly three years of later data untouched, for example:

- development: events before `2023-01-01T00:00:00+00:00`
- confirmation: events from `2023-01-01T00:00:00+00:00`

The script refuses to run the confirmation stage when the untouched confirmation block has fewer than the frozen B-level minimum of 10,000 events.

## Frozen model contract

- Candidate selection uses development labels only.
- Candidate search may include atomic conditions and pairwise conjunctions.
- The selected candidate is frozen before confirmation evaluation.
- Its probability is estimated from development-selected events only.
- On confirmation data, the candidate changes the probability only for rows satisfying the frozen predicate; non-candidate rows retain the development baseline probability.
- Confirmation rows are partitioned chronologically into fixed-size folds.
- No confirmation label can modify the candidate, threshold, probability, or fold assignment.

## B-level acceptance

The confirmation harness preserves the existing criteria; it does not relax them:

- at least 10,000 independent confirmation OOS events
- positive aggregate Brier improvement
- 95% bootstrap CI for fold improvement entirely above zero
- paired sign-permutation p < 0.01
- two-sided sign-test p < 0.05
- at least 70% of confirmation folds improve
- label-shuffle negative control
- temporal-leakage negative control
- independent source-to-result and walk-forward audits remain required

`B_LEVEL_PASS` is valid only when every required criterion is satisfied. Otherwise the scientific result is `NO_EDGE_OR_INCONCLUSIVE`.

## Important interpretation

A positive development score is not evidence of an edge. A positive confirmation score that fails one or more B-level criteria is also not an edge. The only acceptable promotion path is:

`DISCOVERY → FROZEN HYPOTHESIS → UNTOUCHED CONFIRMATION → ALL B-LEVEL GATES PASS → EDGE`

All failures, inconclusive results, and successful gate evaluations remain permanent evidence events in the unified ledger. A later fix or new experiment creates a new event; it does not erase the earlier result.
