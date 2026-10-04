#ifndef QROS_LOW_LATENCY_GEOMETRIC_NULL_H
#define QROS_LOW_LATENCY_GEOMETRIC_NULL_H

#include <cstddef>

namespace quant::low_latency {

class GeometricNullKernel final {
public:
  // Computes the uniform 1D probability for [p1, p2] within [low, high].
  static void interval_probability(const double* low, const double* high,
                                   const double* p1, const double* p2,
                                   std::size_t n, double* out);

  // Driftless martingale first-passage baseline from open to candle barriers.
  static void first_passage(const double* open, const double* high,
                            const double* low, std::size_t n,
                            double* hit_high, double* hit_low);
};

}  // namespace quant::low_latency

#endif
