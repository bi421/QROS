# QROS Anti-Trap Evidence Filter V1

## Purpose

A conservative, deterministic signal-quality gate for XAUUSD-style candle research. It blocks stale signals, excessive spread/slippage, extreme candle-body impulses, and a level sweep that closes back inside the prior range.

It does **not** identify institutional intent, prove spoofing, infer hidden stop locations, or guarantee a profitable entry. A candle-only input cannot reveal a participant's motive or hidden orders. OTC XAUUSD feeds may not expose a consolidated order book or all liquidity venues.

## Formula contracts

### 1. Signal age

\[
L_{signal}=T_{decision}-T_{event}
\]

The caller supplies `signal_age_ns` from compatible timestamps. If it exceeds a configured maximum, both directions are blocked. A timestamp ordering or clock-domain error must be rejected upstream; do not clamp negative ages to zero.

### 2. Impulse/chasing gate

\[
I_{ATR}=\frac{|C-O|}{ATR}
\]

If \(I_{ATR}>I_{max}\), both directions are blocked for this signal. This is a transparent candle-body/ATR ratio, not a probability. Choose \(I_{max}\) from training data and test out-of-sample; do not tune it on the final test set.

### 3. Rejected range sweep

Upward rejection:

\[
H>H_{prior}\quad\land\quad C\le H_{prior}
\]

\[
S_{up}=\frac{H-H_{prior}}{ATR}
\]

Downward rejection:

\[
L<L_{prior}\quad\land\quad C\ge L_{prior}
\]

\[
S_{down}=\frac{L_{prior}-L}{ATR}
\]

An upward rejected sweep blocks a long signal; a downward rejected sweep blocks a short signal. These are OHLC proxies for rejection at a supplied range boundary. They do not prove stop hunting, spoofing, or a liquidity pool.

### 4. Cost and freshness gates

\[
spread\le spread_{max},\qquad
slippage_{estimated}\le slippage_{max},\qquad
L_{signal}\le L_{max}
\]

If any global gate fails, both directions are blocked. Spread and slippage must use the same price units as the candle prices. If reliable slippage or timestamp data is unavailable, the upstream system should mark the signal unverified rather than fabricate inputs.

## Outputs and limits

The C++ API `evaluate_anti_trap` returns long/short eligibility, a bitmask explaining blocks, impulse in ATR units, wick fractions, and sweep overshoot in ATR units. It does not create an entry order or position sizing.

This V1 does not yet implement retest/continuation confirmation, order-book spoofing detection, hidden-stop inference, cross-venue latency arbitrage, or a calibrated trap probability. Those require additional timestamped point-in-time data and separate empirical tests.

## Validation required before research claims

- Unit/property tests for OHLC invariants, invalid numeric values, thresholds, and all reason-mask combinations.
- Replay using only information available at each decision timestamp; prohibit look-ahead.
- Compare baseline strategy versus filter-enabled strategy on untouched out-of-sample periods.
- Report trade count, expectancy after spread/slippage, maximum drawdown, false-block rate, and confidence intervals.
- Test across multiple market regimes and provider feeds. A rule that merely reduces trade count is not evidence of improved edge.

No orders are placed or executed by this component.
