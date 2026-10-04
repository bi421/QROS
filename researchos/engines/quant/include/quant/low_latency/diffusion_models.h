#ifndef QROS_LOW_LATENCY_DIFFUSION_MODELS_H
#define QROS_LOW_LATENCY_DIFFUSION_MODELS_H

#include <cstddef>

namespace quant::low_latency {

class DiffusionModelKernel final {
public:
  // Constant-coefficient heat-kernel density:
  // p(x,t) = exp(-(x-mean)^2/(4Dt)) / sqrt(4*pi*D*t).
  static void heat_density(const double* x, const double* mean,
                           const double* diffusion, const double* time,
                           std::size_t n, double* out);

  // Probability of landing in [lower, upper] under the same diffusion kernel.
  static void heat_interval_probability(const double* mean,
                                        const double* diffusion,
                                        const double* time,
                                        const double* lower,
                                        const double* upper,
                                        std::size_t n, double* out);

  // GBM Fokker-Planck transition density in log-price form.
  // Returns density with respect to price S>0:
  // p(S,t|S0) = exp(-(ln(S/S0)-(mu-sigma^2/2)t)^2/(2*sigma^2*t))
  //            / (S*sigma*sqrt(2*pi*t)).
  static void gbm_lognormal_density(const double* spot, const double* price,
                                    const double* drift, const double* volatility,
                                    const double* time, std::size_t n, double* out);
};

}  // namespace quant::low_latency

#endif
