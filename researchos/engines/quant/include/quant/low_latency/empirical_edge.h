#ifndef QROS_LOW_LATENCY_EMPIRICAL_EDGE_H
#define QROS_LOW_LATENCY_EMPIRICAL_EDGE_H
#include <cstddef>
namespace quant::low_latency {
class EmpiricalEdgeKernel final {
public:
  // Writes empirical p, geometric p, delta p, z-score, two-sided normal p-value.
  static void compute(const double* empirical_probability,
                      const double* geometric_probability,
                      const double* sample_size, std::size_t n, double* out);
};
}  // namespace quant::low_latency
#endif
