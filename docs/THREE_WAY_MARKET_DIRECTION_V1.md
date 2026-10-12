# Three-Way Market Direction Output V1

## Contract

The canonical QROS decision pipeline emits exactly one direction label:

- `UP`
- `DOWN`
- `NEUTRAL`

The output is derived from the existing `ProbabilityAssessment` distribution. This addition does not replace the evidence aggregation or probability calculation layers.

## Rule

Given the existing assessment probabilities:

- (p_U): bullish probability
- (p_D): bearish probability
- (p_N): neutral probability

The selected direction is the unique class with the greatest probability. If the greatest probability is tied between two or more classes, the output is `NEUTRAL`. The three probabilities must be finite, within [0, 1], and sum to 1 within the configured numerical tolerance. Invalid distributions raise `ValueError`; they are not converted into a directional guess.

## Pipeline integration

`DecisionPipelineResult.direction_forecast` exposes the typed `DirectionForecast`. `DecisionPipelineResult.to_dict()` adds a `direction_forecast` object containing the direction, all three probabilities, the maximum probability, calculation version, and assessment hash.

The calculation remains research-only. This contract defines the output shape and deterministic classification rule; it does not claim that an upstream probability distribution is calibrated or that the direction is correct in future markets.
