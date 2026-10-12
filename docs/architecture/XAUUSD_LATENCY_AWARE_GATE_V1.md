# XAUUSD Latency-Aware Research Gate (Additive V1)

## Purpose

QROS should minimize avoidable compute delay and reject stale or temporally
invalid inputs. It cannot make end-to-end market latency zero: provider delay,
network transit, clock error, exchange/broker infrastructure, and market impact
remain external variables.

This component is an additive standard-library contract. It does not alter
existing engine mathematics, fetch live quotes, calibrate probabilities, place
orders, or imply that live feed wiring is already deployed.

## Contract

`researchos.orchestration.latency.LatencyGate` checks:

- source timestamp freshness against a **source-specific** `max_source_age_ms`;
- timestamps too far in the future against `max_future_skew_ms`;
- measured compute duration against `max_processing_ms`;
- timezone validity and malformed durations.

Any violation returns `REJECT` with stable reason codes. The caller must not
consume a rejected snapshot for a new research decision. No silent fallback to
older data is permitted.

Use UTC-aware wall-clock timestamps for source/evaluation time comparison.
Use `time.perf_counter_ns()` via `start_monotonic_timer()` and `elapsed_ns()`
for elapsed compute time. Do not measure compute duration by subtracting wall
clock timestamps, because clock adjustments can make that measurement wrong.

## Integration pattern

1. Capture source timestamp and source identity at market-data ingestion.
2. Capture monotonic start time before parsing/normalization and calculations.
3. Run the existing engine without changing its math.
4. Measure elapsed processing time with `elapsed_ns(started_ns)`.
5. Call `LatencyGate(policy).assess(source_as_of=..., evaluated_at=...,
   processing_ns=...)` before publishing the result.
6. If rejected, emit the reason code and keep the run in an insufficient /
   rejected evidence state. Do not retry forever or silently substitute stale
   data.
7. Record source identity, source timestamp, observed age, processing duration,
   policy version, and rejection reason for later audit.

## Policy calibration

Do not use one hard-coded age limit for every timeframe. M15 decision bars,
H1/H4/D1 context bars, macro releases, and streaming quote/tick data have
different expected update schedules. Configure per source and per timeframe,
account for closed-bar semantics, provider publication delays, and clock skew.
Thresholds must be calibrated from observed production telemetry; example
numbers in tests are fixtures, not recommended trading thresholds.

## Latency budget decomposition

Measure separately, where instrumentation exists:

- source/publication age;
- ingestion and normalization;
- feature / engine computation;
- evidence fusion / report assembly;
- queue wait and worker scheduling;
- database persistence;
- network transit and external provider delay.

Optimize p50, p95, p99 and maximum durations, not just averages. A fast compute
path does not make stale input fresh. When required source freshness cannot be
proven, fail closed.

## Status

- IMPLEMENTED: immutable policy/assessment contracts, monotonic timing helpers,
  stable fail-closed reasons, unit tests.
- NOT YET PROVEN: measured production p50/p95/p99; live feed/provider timestamps;
  end-to-end network or broker latency; source-specific thresholds.
- NOT YET WIRED: the live ingestion/adapter path must call the gate before
  accepting/publishing source data. Adding this module alone does not enforce
  a gate on existing callers.
- OUT OF SCOPE: order execution. QROS remains a research/evidence system.
