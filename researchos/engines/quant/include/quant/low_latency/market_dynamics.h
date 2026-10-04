#ifndef QROS_LOW_LATENCY_MARKET_DYNAMICS_H
#define QROS_LOW_LATENCY_MARKET_DYNAMICS_H

#include <cstddef>

namespace quant::low_latency {

class MarketDynamicsKernel final {
public:
  // v = delta_price / dt
  // p = volume * v
  // Writes [velocity, momentum] per row.
  static void velocity_momentum(const double* delta_price,
                                const double* volume,
                                const double* time_delta,
                                std::size_t n, double* out);

  // F = delta(momentum) / dt.
  static void force(const double* momentum,
                    const double* previous_momentum,
                    const double* time_delta,
                    std::size_t n, double* out);
};

}  // namespace quant::low_latency

#endif
