#include "quant/low_latency/empirical_edge.h"
#include <cmath>
#include <stdexcept>
namespace quant::low_latency {
void EmpiricalEdgeKernel::compute(const double* empirical_probability,
                                  const double* geometric_probability,
                                  const double* sample_size, std::size_t n,
                                  double* out) {
  if (n == 0) return;
  if (!empirical_probability || !geometric_probability || !sample_size || !out)
    throw std::invalid_argument("EmpiricalEdge received a null buffer");
  for (std::size_t i=0; i<n; ++i) {
    const double empirical=empirical_probability[i], geometric=geometric_probability[i],
                 count=sample_size[i];
    if (!std::isfinite(empirical) || !std::isfinite(geometric) ||
        !std::isfinite(count) || empirical<0.0 || empirical>1.0 ||
        geometric<0.0 || geometric>1.0 || !(count>0.0))
      throw std::invalid_argument("invalid empirical-edge inputs");
    const double delta=empirical-geometric;
    const double variance=geometric*(1.0-geometric)/count;
    if (!(variance > 0.0))
      throw std::invalid_argument("normal approximation requires geometric probability strictly between 0 and 1");
    const double z=delta/std::sqrt(variance);
    const double p=std::erfc(std::abs(z)/std::sqrt(2.0));
    const std::size_t j=i*5;
    out[j]=empirical;
    out[j+1]=geometric;
    out[j+2]=delta;
    out[j+3]=z;
    out[j+4]=p;
  }
}
}  // namespace quant::low_latency
