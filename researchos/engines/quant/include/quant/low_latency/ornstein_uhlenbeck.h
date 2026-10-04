#ifndef QROS_LOW_LATENCY_ORNSTEIN_UHLENBECK_H
#define QROS_LOW_LATENCY_ORNSTEIN_UHLENBECK_H

#include <cstddef>

namespace quant::low_latency {

class OrnsteinUhlenbeckKernel final {
public:
  // Conditional mean and variance of
  // dx = theta*(mu-x)dt + sigma*dW.
  // Writes mean and variance as adjacent values per row: [mean, variance].
  static void transition_moments(const double* x0, const double* theta,
                                 const double* mu, const double* sigma,
                                 const double* time, std::size_t n, double* out);

  // Conditional probability of x(t) landing in [lower, upper].
  static void interval_probability(const double* x0, const double* theta,
                                   const double* mu, const double* sigma,
                                   const double* time, const double* lower,
                                   const double* upper, std::size_t n,
                                   double* out);
};

}  // namespace quant::low_latency

#endif
