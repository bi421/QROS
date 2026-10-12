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

## Statistical limitation

The linear penalty is a heuristic score, not automatically a real-world success probability. Illustrative test-only coefficients (P_base=0.85, alpha=0.001/ms, beta=0.002/VXY-unit, gamma=0.01/DXY-point) yield 83.2% for the supplied calm example and 76.6% for the supplied stress example. They do not reproduce the claimed 82–88% calm and 35–45% stress ranges. This mismatch is intentional evidence that coefficients must not be guessed.

To claim empirical probability, fit only on training data, freeze coefficients, evaluate on strictly later out-of-sample periods, check reliability/Brier score, and stratify by session/news regime and instrument/feed. Define success precisely (TP before SL within a fixed horizon after estimated costs); order-fill success and trade-outcome success are different targets. Avoid look-ahead and survivorship bias. Until documented acceptance criteria pass, keep calibration_verified=false.

No live trading or order execution is added. Optional Python tests may skip if the extension is unavailable; skipped tests do not prove binding execution.
