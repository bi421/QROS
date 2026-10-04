# QROS Quant Mathematics Layer

The quant_math package is the deterministic computation boundary for
probability/statistics, Bayesian updating, MLE, correlation, regression,
Monte Carlo, matrix algebra, multivariate distance and market geometry.

Market geometry includes slope, angle, vector displacement, Euclidean
distance, three-point curvature, pivot-derived support/resistance and
regression R-squared as a trend-strength measurement.

The QuantMathEvidenceProvider is the explicit boundary into the existing
EvidenceAggregator. It emits one provenance-bearing QuantEngine evidence
item. The normal decision flow remains:

market observations -> quant mathematics -> evidence fusion -> probability
engine -> risk engine -> governance -> human review.

The provider does not place orders. A positive slope is not itself a claim of
trading edge; it is directional quantitative evidence whose strength is
bounded by the measured trend fit.
