#include "quant/market/multivariate_probability.h"
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>
namespace quant::microstructure {
namespace {
void require_finite(double value, const char* name) {
  if (!std::isfinite(value)) throw std::invalid_argument(std::string(name) + " must be finite");
}
}
MultivariateProbabilityResult evaluate_multivariate_probability(const MultivariateProbabilityInput& x) {
  require_finite(x.base_probability, "base_probability");
  require_finite(x.latency_ms, "latency_ms");
  require_finite(x.vxy, "vxy");
  require_finite(x.dxy, "dxy");
  require_finite(x.dxy_baseline, "dxy_baseline");
  require_finite(x.alpha_per_ms, "alpha_per_ms");
  require_finite(x.beta_per_vxy_unit, "beta_per_vxy_unit");
  require_finite(x.gamma_per_dxy_point, "gamma_per_dxy_point");
  require_finite(x.gate_threshold, "gate_threshold");
  if (x.base_probability < 0 || x.base_probability > 1 || x.latency_ms < 0 ||
      x.vxy < 0 || x.alpha_per_ms < 0 || x.beta_per_vxy_unit < 0 ||
      x.gamma_per_dxy_point < 0 || x.gate_threshold < 0 || x.gate_threshold > 1)
    throw std::invalid_argument("probability, latency, volatility, coefficients, or threshold out of range");
  const double lp=x.alpha_per_ms*x.latency_ms;
  const double vp=x.beta_per_vxy_unit*x.vxy;
  const double dp=x.gamma_per_dxy_point*std::abs(x.dxy-x.dxy_baseline);
  require_finite(lp,"latency_penalty"); require_finite(vp,"volatility_penalty");
  require_finite(dp,"dxy_penalty");
  const double raw=x.base_probability-lp-vp-dp;
  require_finite(raw,"raw_probability");
  MultivariateProbabilityResult out;
  out.latency_penalty=lp; out.volatility_penalty=vp; out.dollar_deviation_penalty=dp;
  out.estimated_success_probability=std::clamp(raw,0.0,1.0);
  out.calibration_verified=x.calibration_verified;
  out.research_gate_pass=x.calibration_verified && out.estimated_success_probability>=x.gate_threshold;
  return out;
}
}
