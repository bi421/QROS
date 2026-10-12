#pragma once
namespace quant::microstructure {
struct MultivariateProbabilityInput {
  double base_probability{0.0}, latency_ms{0.0}, vxy{0.0}, dxy{0.0}, dxy_baseline{0.0};
  double alpha_per_ms{0.0}, beta_per_vxy_unit{0.0}, gamma_per_dxy_point{0.0};
  double gate_threshold{0.70};
  bool calibration_verified{false};
};
struct MultivariateProbabilityResult {
  double latency_penalty{0.0}, volatility_penalty{0.0}, dollar_deviation_penalty{0.0};
  double estimated_success_probability{0.0};
  bool calibration_verified{false}, research_gate_pass{false};
};
// P_hat = clamp(P_base - alpha*latency_ms - beta*VXY
//               - gamma*abs(DXY-DXY_baseline), 0, 1).
// Coefficients must be calibrated externally. Gate passes only if calibration
// is explicitly verified and score >= threshold. Research-only; no order I/O.
MultivariateProbabilityResult evaluate_multivariate_probability(
    const MultivariateProbabilityInput& input);
}
