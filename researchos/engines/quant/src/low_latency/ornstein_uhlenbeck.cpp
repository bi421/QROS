#include "quant/low_latency/ornstein_uhlenbeck.h"

#include <cmath>
#include <stdexcept>

namespace quant::low_latency {
namespace {
constexpr double kSqrtTwo = 1.414213562373095048801688724209698079;

double normal_cdf(double z) noexcept {
  return 0.5 * std::erfc(-z / kSqrtTwo);
}

void validate(double x0, double theta, double mu, double sigma, double time) {
  if (!std::isfinite(x0) || !std::isfinite(theta) || !std::isfinite(mu) ||
      !std::isfinite(sigma) || !std::isfinite(time))
    throw std::invalid_argument("OU inputs must be finite");
  if (!(theta > 0.0) || !(sigma > 0.0) || !(time > 0.0))
    throw std::invalid_argument("OU theta, sigma and time must be positive");
}

}  // namespace

void OrnsteinUhlenbeckKernel::transition_moments(
    const double* x0, const double* theta, const double* mu,
    const double* sigma, const double* time, std::size_t n, double* out) {
  if (n == 0) return;
  if (!x0 || !theta || !mu || !sigma || !time || !out)
    throw std::invalid_argument("OU received a null buffer");

  for (std::size_t i = 0; i < n; ++i) {
    validate(x0[i], theta[i], mu[i], sigma[i], time[i]);
    const double decay = std::exp(-theta[i] * time[i]);
    const double variance =
        (sigma[i] * sigma[i]) * (-std::expm1(-2.0 * theta[i] * time[i])) /
        (2.0 * theta[i]);
    out[2 * i] = mu[i] + (x0[i] - mu[i]) * decay;
    out[2 * i + 1] = variance;
  }
}

void OrnsteinUhlenbeckKernel::interval_probability(
    const double* x0, const double* theta, const double* mu,
    const double* sigma, const double* time, const double* lower,
    const double* upper, std::size_t n, double* out) {
  if (n == 0) return;
  if (!x0 || !theta || !mu || !sigma || !time || !lower || !upper || !out)
    throw std::invalid_argument("OU received a null buffer");

  for (std::size_t i = 0; i < n; ++i) {
    validate(x0[i], theta[i], mu[i], sigma[i], time[i]);
    if (!std::isfinite(lower[i]) || !std::isfinite(upper[i]) ||
        upper[i] < lower[i])
      throw std::invalid_argument("invalid OU interval");

    const double decay = std::exp(-theta[i] * time[i]);
    const double mean = mu[i] + (x0[i] - mu[i]) * decay;
    const double variance =
        (sigma[i] * sigma[i]) * (-std::expm1(-2.0 * theta[i] * time[i])) /
        (2.0 * theta[i]);
    const double sd = std::sqrt(variance);
    out[i] = normal_cdf((upper[i] - mean) / sd) -
             normal_cdf((lower[i] - mean) / sd);
  }
}

}  // namespace quant::low_latency
