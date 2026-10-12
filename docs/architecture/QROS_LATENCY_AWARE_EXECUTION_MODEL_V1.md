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

## 2. User-specified price movement equation — implemented as numerical integration

The intended relationship is:

\[
P_{actual}(t+\Delta t)=P_{expected}(t)+\int_t^{t+\Delta t}v(\tau)\,d\tau+\epsilon
\]

The additive C++ API `project_price_by_velocity_integral` now integrates supplied velocity observations over elapsed time using the composite trapezoidal rule:

\[
\int_t^{t+\Delta t}v(\tau)\,d\tau
\approx \sum_{i=1}^{n-1}\frac{v_{i-1}+v_i}{2}(t_i-t_{i-1})
\]

Inputs are elapsed sample times in seconds (starting at zero), matching velocity samples in price units per second, the expected starting price, and an explicit residual `epsilon_price`. Times must be finite and strictly increasing; sample arrays must have equal length and at least two observations. Invalid inputs and non-finite results fail closed.

**Scientific boundary:** the integral is only as accurate as the velocity samples and sampling frequency. The trapezoidal rule is a numerical approximation, not exact knowledge of the continuous path. If velocity is estimated from future candles, the result leaks future information; live-style/backtest evaluation must only use samples available by the simulated decision time. The residual is explicit scenario input, not generated noise or a calibrated prediction.

The previous constant-drift function `project_price_after_latency` remains as a simplified baseline, not a substitute for the velocity-integral model.

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
- `project_price_by_velocity_integral(expected_price, sample_times_seconds, velocity_price_per_second, epsilon_price=0)`
- `project_price_after_latency(reference_price, drift_price_per_second, latency_ns, epsilon_price=0)` — simplified constant-drift baseline
- `estimate_execution_penalty(latency_ns, volatility_price_per_sqrt_second, drift_price_per_second, order_size, available_liquidity, impact_coefficient)`

C++ tests cover integration results, malformed samples, latency overflow, timestamp ordering, baseline projection and penalty guards. Python binding smoke tests are optional; a skipped test is not evidence that the extension compiled or ran.

## 5. What is and is not proven

**Implemented in source:** deterministic arithmetic, numerical velocity integration, unit-aware parameter names, overflow/finite-value guards, timestamp-order guard, nanobind exposure and C++ tests.

**Not proven until exact-SHA CI completes:** compilation, all tests, extension import, runtime performance, end-to-end replay integration.

**Not implemented here:** production instrumentation that measures each latency component; live provider latency collection; an event-driven fill simulator; order-book queue position; empirical calibration of velocity/drift/volatility/impact; calibrated probability of adverse execution. Those require provider-specific evidence and must not be represented as completed.

No order execution is added.
