# Market-state sequence integrity guard

## Status

Implemented as an additive, pure validation contract. Not wired into live feed
ingestion or the research-run worker. No provider sequence semantics have been
verified against a live broker or futures venue.

## Contract

`researchos/orchestration/market_state_sequence_guard.py` evaluates
`EventClock` records in **ingestion order**, independently for each source.
It requires a positive integer sequence and rejects:

- `SEQUENCE_MISSING_OR_INVALID`: absent, non-integer, boolean, zero, or negative sequence.
- `SEQUENCE_DUPLICATE`: the current sequence equals the previous sequence for that source.
- `SEQUENCE_REGRESSION`: the current sequence moves backward.
- `SEQUENCE_GAP`: one or more sequence numbers were skipped.

Sequence counters may start at any positive value and are independent across
sources. The report preserves stable global and per-source issue codes. The
guard intentionally does not sort or repair events and does not infer that a
gap is harmless. Event-time ordering is a separate point-in-time concern:
late-arriving event timestamps can be legitimate when sequence order remains
valid, but downstream decisions must still enforce their as-of cutoff.

## Integration boundary

Callers should run this guard on each source's raw event stream before deriving
features or claiming a complete replay. A `valid=false` report must prevent a
complete-stream/replay claim. This module does not modify the existing market
state calculations, fetch feeds, persist results, produce probabilities, or
enable order execution.

## Verification

Unit tests cover independent source counters, duplicates, regressions, gaps,
missing/invalid sequences, late event timestamps, and invalid input types.
Repository CI must pass for the exact pull-request head before merge. Live
provider behavior, reconnect/reset semantics, and sequence guarantees remain
external dependencies.
