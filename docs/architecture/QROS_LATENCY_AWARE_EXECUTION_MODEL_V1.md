# QROS Latency-Aware Execution Model V1

## Scope

This is an additive, deterministic research model. It does not route or place orders, does not guarantee fill prices, and does not assert that inputs have been calibrated against a live XAUUSD provider. Existing quant formulas, event replay and orchestration are unchanged.

## 1. Measured latency decomposition

For measured durations, in nanoseconds:

\[
L_{total}=L_{network}+L_{serialization}+L_{queue}+L_{processing}
\]

The C++ API `LatencyBreakdown` sums those four non-negative duration fields with overflow checks. Each duration must be measured at its actual boundary. A round-trip ping is not a valid substitute for one-way feed latency; it includes a different path and may be asymmetric. Prefer monotonic clocks for local duration measurements.

Observed source-to-ingest delay is:

\[
L_{feed}=T_{ingest}-T_{event}
\]

This subtraction is meaningful only when both timestamps use compatible, synchronized UTC epoch clocks. If ingest precedes event time, the API fails closed and asks for clock-synchronization investigation rather than clamping the delay to zero. Source timestamp accuracy remains a provider dependency.

## 2. Deterministic price projection

For reference price \(P_0\), drift \(\mu\) in price units per second, latency \(\Delta t\) in seconds, and explicitly supplied scenario residual \(\epsilon\):

\[
P_{projected}=P_0+\mu\Delta t+\epsilon
\]

The residual is an input scenario, not a generated random draw or a prediction. The function validates finite values and requires the projected price to remain positive.

## 3. Expected adverse-move / impact penalty

The implemented baseline model assumes a zero-mean Gaussian diffusion for the random price component. Given volatility \(\sigma\) in price units per square-root second, order size \(Q\), available liquidity \(D>0\), and calibrated impact coefficient \(k\) in price units per participation ratio:

\[
r=\frac{Q}{D}
\]

\[
C_{drift}=|\mu|\Delta t
\]

\[
C_{diffusion}=\sigma\sqrt{\Delta t}\sqrt{\frac{2}{\pi}}
\]

\[
C_{impact}=kr
\]

\[
C_{expected}=C_{drift}+C_{diffusion}+C_{impact}
\]

This produces an expected price-unit penalty, not a probability. Convert it to currency only with a correctly specified instrument contract multiplier and position units. The linear impact term is a baseline assumption, not a universal market-impact law. Calibrate \(k\), volatility and drift from point-in-time training data, and validate out-of-sample. If depth is unavailable, do not invent \(D\); mark the penalty unavailable or use an explicitly declared conservative scenario.

## 4. C++20 / nanobind API

New isolated module: `cpp_quant_engine.qros_latency`, CMake target `qros_latency`.

- `total_latency_ns(LatencyBreakdown)`
- `observed_feed_latency_ns(event_time_ns, ingest_time_ns)`
- `project_price_after_latency(reference_price, drift_price_per_second, latency_ns, epsilon_price=0)`
- `estimate_execution_penalty(latency_ns, volatility_price_per_sqrt_second, drift_price_per_second, order_size, available_liquidity, impact_coefficient)`

The API rejects invalid numeric inputs and arithmetic overflow. C++ unit tests and optional Python binding smoke tests cover the contract. A skipped optional binding test is not evidence that the extension compiled or ran.

## 5. What is and is not proven

**Implemented in source:** deterministic arithmetic, unit-aware parameter names, overflow/finite-value guards, timestamp-order guard, nanobind exposure, C++ tests and optional binding tests.

**Not proven until exact-SHA CI completes:** compilation, all tests, extension import, runtime performance, end-to-end replay integration.

**Not implemented here:** instrumentation hooks that measure each latency component in production; live provider latency collection; an event-driven fill simulator; order-book queue position; empirical calibration of drift/volatility/impact; calibrated probability of adverse execution. Those require provider-specific evidence and must not be represented as completed.

No order execution is added.
