# Three-state probability decision gate

## Contract

The C++20 kernel evaluates a supplied, frozen model; it does not train or calibrate the model.

The six standardized features, in fixed order, are:
1. price_return_z
2. volume_z
3. latency_z
4. ofi_z
5. vxy_z
6. dxy_return_z

The feature standardization parameters must come from the training split and be frozen before validation/test evaluation. The model contains 18 row-major weights (six each for bearish, neutral, bullish) and three biases. Output probability order is bearish, neutral, bullish.

The kernel computes stable softmax probabilities. A state is only directional when the relevant bearish/bullish probability is strictly greater than the configured threshold and every safety gate passes. Otherwise the state is neutral (0). Invalid shapes, non-finite model inputs, stale DXY, excessive latency, excessive VXY, or excessive absolute DXY move fail closed.

Default safety limits (250 ms, VXY level 30, absolute DXY move 1%) are engineering defaults for tests and must be validated against the actual feed/provider, instrument, and sampling interval before research use. They are not universal market truths or production-approved values.

## Output destination

The decision belongs in the completed QROS research-run report/evidence artifact, not in broker integration or an execution endpoint. The report should include:
- timestamp and source-data/dataset SHA-256;
- model identifier/version and frozen feature-scaling version;
- p_bearish, p_neutral, p_bullish, and their sum;
- threshold, state (-1, 0, +1), safety pass/fail, and machine-readable reason;
- raw safety observations and active limits;
- calibration/OOS validation status.

For time-series research, persist one decision record per evaluated timestamp and show the latest record plus state history in the report. A failed gate must remain visible as state=0 with its reason; do not silently drop it. Keep the artifact immutable and tied to the exact dataset and model hashes. The research-run summary API can expose a report link/status, but this result must never trigger orders.

## Evidence boundary

This kernel provides deterministic arithmetic and a fail-closed decision rule. It does not prove predictive edge, probability calibration, or profitability. Until model weights, scaling statistics, thresholds, and safety limits are fitted/selected on training data and then evaluated on chronologically separate validation and out-of-sample data, label output as experimental/unvalidated. Do not publish placeholder or hand-picked weights as learned model parameters.
