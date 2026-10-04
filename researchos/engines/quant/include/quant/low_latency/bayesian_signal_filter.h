#ifndef QROS_LOW_LATENCY_BAYESIAN_SIGNAL_FILTER_H
#define QROS_LOW_LATENCY_BAYESIAN_SIGNAL_FILTER_H
#include <cstddef>
namespace quant::low_latency {
class BayesianSignalFilter final {
public:
  static void filter_binary(const double* signal, const double* p_signal_given_up,
                            const double* p_signal_given_down, std::size_t count,
                            double prior_probability_up, double* posterior_probability_up);
};
}  // namespace quant::low_latency
#endif
