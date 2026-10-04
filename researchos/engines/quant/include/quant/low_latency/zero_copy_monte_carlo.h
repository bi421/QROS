#ifndef QROS_LOW_LATENCY_ZERO_COPY_MONTE_CARLO_H
#define QROS_LOW_LATENCY_ZERO_COPY_MONTE_CARLO_H
#include <cstddef>
namespace quant::low_latency {
struct GBMTerminalConfig final {
  double spot{100.0};
  double drift{0.05};
  double volatility{0.20};
  double time_horizon{1.0};
  double dt{0.0};
};
class ZeroCopyMonteCarlo final {
public:
  static void gbm_terminal_from_shocks(const double* shocks, std::size_t num_paths,
                                       std::size_t num_steps, const GBMTerminalConfig& config,
                                       double* terminal_values);
};
}  // namespace quant::low_latency
#endif
