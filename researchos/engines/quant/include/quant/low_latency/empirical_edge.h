#ifndef QROS_LOW_LATENCY_EMPIRICAL_EDGE_H
#define QROS_LOW_LATENCY_EMPIRICAL_EDGE_H

#include <cstddef>

namespace quant::low_latency {

struct EmpiricalEdge final {
  double empirical_probability;
  double geometric_probability;
  double delta_probability;
  double z_score;
  double two_sided_p_value;
};

class EmpiricalEdgeKernel final {
public:
  // empirical_probability and geometric_probability are probabilities in [0, 1].
  // sample_size is the independent Bernoulli sample size used for the null SE.
  static void compute(const double* empirical_probability,
                      const double* geometric_probability,
                      const double* sample_size, std::size_t n,
                      EmpiricalEdge* out);
};

}  // namespace quant::low_latency

#endif
