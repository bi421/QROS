#include "quant/low_latency/empirical_edge.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace quant::low_latency {

void EmpiricalEdgeKernel::compute(const double* empirical_probability,
                                  const double* geometric_probability,
                                  const double* sample_size, std::size_t n,
                                  EmpiricalEdge* out) {
  if (n == 0) return;
  if (!empirical_probability || !geometric_probability || !sample_size || !out) {
    throw std::invalid_argument("EmpiricalEdge received a null buffer");
  }

  constexpr double kMinProbability = 0.0;
  constexpr double kMaxProbability = 1.0;

  for (std::size_t i = 0; i < n; ++i) {
    const double empirical = empirical_probability[i];
    const double geometric = geometric_probability[i];
    const double count = sample_size[i];

    if (!std::isfinite(empirical) || !std::isfinite(geometric) ||
        !std::isfinite(count) || empirical < kMinProbability ||
        empirical > kMaxProbability || geometric < kMinProbability ||
        geometric > kMaxProbability || !(count > 0.0)) {
      throw std::invalid_argument("invalid empirical-edge inputs");
    }

    const double delta = empirical - geometric;
    const double variance = geometric * (1.0 - geometric) / count;
    const double z = variance > 0.0 ? delta / std::sqrt(variance) : 0.0;
    const double p = variance > 0.0 ? std::erfc(std::abs(z) / std::sqrt(2.0)) : 0.0;

    out[i] = EmpiricalEdge{empirical, geometric, delta, z, p};
  }
}

}  // namespace quant::low_latency
