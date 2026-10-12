# QROS Multivariate Probability Gate V1

For point-in-time inputs the deterministic score is:

\[
\hat P=\operatorname{clip}_{[0,1]}(P_{base}-\alpha\Delta t_{ms}-\beta VXY-\gamma|DXY-DXY_{baseline}|)
\]

Coefficient units are probability per millisecond, probability per VXY unit, and probability per DXY point. Latency is milliseconds. VXY is a caller-supplied nonnegative volatility/risk index; DXY and its baseline must use the same scale.

## Safety contract

- Reject non-finite values, negative latency/volatility/coefficients, invalid probability ranges, and arithmetic overflow.
- Clamp the displayed score to [0, 1].
- The research gate passes only if calibration is explicitly verified and the score meets the configured threshold (default 0.70).
- Unverified calibration means the gate remains closed, regardless of score.
- This is a research eligibility flag only. It does not place, cancel, block, or modify live orders.

## Deterministic fixture arithmetic (not empirical results)

For test fixtures only, use P_base=0.85, alpha=0.001/ms, beta=0.002/VXY-unit, gamma=0.01/DXY-point.

Calm example:
0.85 - (0.001*5) - (0.002*6.5) - (0.01*abs(101.2-101.2)) = 0.832 (83.2%).

Stress example:
0.85 - (0.001*50) - (0.002*14.5) - (0.01*abs(106.8-101.2)) = 0.715 (71.5%).

Therefore these illustrative coefficients do NOT reproduce the claimed 82–88% calm and 35–45% stress ranges. That mismatch is intentional: coefficients must not be reverse-engineered or guessed to make a desired result appear true.

## Statistical limitation

The linear penalty is a heuristic score, not automatically a real-world success probability. To claim empirical probability, fit only on training data, freeze coefficients, evaluate on strictly later out-of-sample periods, check reliability/Brier score, and stratify by session/news regime and instrument/feed. Define success precisely (TP before SL within a fixed horizon after estimated costs); order-fill success and trade-outcome success are different targets. Avoid look-ahead and survivorship bias. Until documented acceptance criteria pass, keep calibration_verified=false.

No live trading or order execution is added. Optional Python tests may skip if the extension is unavailable; skipped tests do not prove binding execution.
