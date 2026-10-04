#include "quant/low_latency/market_dynamics.h"

#include <cmath>
#include <stdexcept>

namespace quant::low_latency {

void MarketDynamicsKernel::velocity_momentum(
    const double* delta_price, const double* volume,
    const double* time_delta, std::size_t n, double* out) {
  if (n == 0) return;
  if (!delta_price || !volume || !time_delta || !out)
    throw std::invalid_argument("MarketDynamics received a null buffer");

  for (std::size_t i = 0; i < n; ++i) {
    if (!std::isfinite(delta_price[i]) || !std::isfinite(volume[i]) ||
        !std::isfinite(time_delta[i]) || !(volume[i] >= 0.0) ||
        !(time_delta[i] > 0.0))
      throw std::invalid_argument("invalid velocity/momentum inputs");

    const double velocity = delta_price[i] / time_delta[i];
    out[2 * i] = velocity;
    out[2 * i + 1] = volume[i] * velocity;
  }
}

void MarketDynamicsKernel::force(
    const double* momentum, const double* previous_momentum,
    const double* time_delta, std::size_t n, double* out) {
  if (n == 0) return;
  if (!momentum || !previous_momentum || !time_delta || !out)
    throw std::invalid_argument("MarketDynamics received a null buffer");

  for (std::size_t i = 0; i < n; ++i) {
    if (!std::isfinite(momentum[i]) || !std::isfinite(previous_momentum[i]) ||
        !std::isfinite(time_delta[i]) || !(time_delta[i] > 0.0))
      throw std::invalid_argument("invalid force inputs");
    out[i] = (momentum[i] - previous_momentum[i]) / time_delta[i];
  }
}

}  // namespace quant::low_latency
