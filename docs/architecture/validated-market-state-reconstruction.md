# Sequence-validated market-state reconstruction

## Purpose

This additive wrapper connects the sequence-integrity report to the existing
market-state reconstruction engine. It does not alter the engine's feature
calculations.

## Contract

Use `researchos/orchestration/validated_market_state_reconstruction.py` and
supply the raw `EventClock` stream in ingestion order, alongside the
corresponding quote, order-book, trade-flow, and macro inputs.

- If any source has a missing/invalid, duplicate, regressing, or gapped sequence,
  the wrapper returns `SEQUENCE_INTEGRITY_FAILED`, with the report and
  `market_state=None`. The engine is not called.
- If the supplied clock stream is valid, the existing reconstruction engine is
  called unchanged and the report is returned with its state.
- The wrapper does not sort events, repair sequence gaps, generate probabilities,
  enable execution, or persist results.

## Important limitation

This is an explicit integration API, not yet wired into a live provider adapter,
dataset replay CLI, or production worker. The caller is responsible for supplying
the complete raw event stream; the wrapper cannot prove completeness if callers
omit events. Live venue sequence/reset/reconnect semantics remain unverified.

## Verification

Tests assert invalid streams block reconstruction, valid streams preserve the
existing engine output boundary (`probabilities=None`,
`execution_enabled=False`), and the engine is never invoked after sequence
validation fails. Merge only after exact-head CI and Git Governance pass.
