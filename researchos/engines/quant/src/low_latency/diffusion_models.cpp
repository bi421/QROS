#include "quant/low_latency/diffusion_models.h"

#include <cmath>
#include <stdexcept>

namespace quant::low_latency {
namespace {

constexpr double kPi = 3.141592653589793238462643383279502884;
constexpr double kSqrtTwo = 1.414213562373095048801688724209698079;

void require_finite(double value, const char* message) {
  if (!std::isfinite(value)) throw std::invalid_argument(message);
}

double normal_cdf(double z) noexcept {
  return 0.5 * std::erfc(-z / kSqrtTwo);
}

}  // namespace

void DiffusionModelKernel::heat_density(const double* x, const double* mean,
                                        const double* diffusion, const double* time,
                                        std::size_t n, double* out) {
  if (n == 0) return;
  if (!x || !mean || !diffusion || !time || !out)
    throw std::invalid_argument("DiffusionModel received a null buffer");

  for (std::size_t i = 0; i < n; ++i) {
    require_finite(x[i], "x must be finite");
    require_finite(mean[i], "mean must be finite");
    require_finite(diffusion[i], "diffusion must be finite");
    require_finite(time[i], "time must be finite");
    if (!(diffusion[i] > 0.0) || !(time[i] > 0.0))
      throw std::invalid_argument("diffusion and time must be positive");

    const double variance = 2.0 * diffusion[i] * time[i];
    const double z = x[i] - mean[i];
    out[i] = std::exp(-(z * z) / (2.0 * variance)) /
             std::sqrt(2.0 * kPi * variance);
  }
}

void DiffusionModelKernel::heat_interval_probability(
    const double* mean, const double* diffusion, const double* time,
    const double* lower, const double* upper, std::size_t n, double* out) {
  if (n == 0) return;
  if (!mean || !diffusion || !time || !lower || !upper || !out)
    throw std::invalid_argument("DiffusionModel received a null buffer");

  for (std::size_t i = 0; i < n; ++i) {
    require_finite(mean[i], "mean must be finite");
    require_finite(diffusion[i], "diffusion must be finite");
    require_finite(time[i], "time must be finite");
    require_finite(lower[i], "lower must be finite");
    require_finite(upper[i], "upper must be finite");
    if (!(diffusion[i] > 0.0) || !(time[i] > 0.0) || upper[i] < lower[i])
      throw std::invalid_argument("invalid diffusion interval");

    const double sd = std::sqrt(2.0 * diffusion[i] * time[i]);
    const double z_low = (lower[i] - mean[i]) / sd;
    const double z_high = (upper[i] - mean[i]) / sd;
    out[i] = normal_cdf(z_high) - normal_cdf(z_low);
  }
}

void DiffusionModelKernel::gbm_lognormal_density(
    const double* spot, const double* price, const double* drift,
    const double* volatility, const double* time, std::size_t n, double* out) {
  if (n == 0) return;
  if (!spot || !price || !drift || !volatility || !time || !out)
    throw std::invalid_argument("GBM density received a null buffer");

  for (std::size_t i = 0; i < n; ++i) {
    require_finite(spot[i], "spot must be finite");
    require_finite(price[i], "price must be finite");
    require_finite(drift[i], "drift must be finite");
    require_finite(volatility[i], "volatility must be finite");
    require_finite(time[i], "time must be finite");
    if (!(spot[i] > 0.0) || !(price[i] > 0.0) ||
        !(volatility[i] > 0.0) || !(time[i] > 0.0))
      throw std::invalid_argument("GBM density requires positive spot, price, volatility and time");

    const double sigma2 = volatility[i] * volatility[i];
    const double log_return =
        std::log(price[i] / spot[i]) - (drift[i] - 0.5 * sigma2) * time[i];
    const double variance = sigma2 * time[i];
    out[i] = std::exp(-(log_return * log_return) / (2.0 * variance)) /
             (price[i] * std::sqrt(2.0 * kPi * variance));
  }
}

}  // namespace quant::low_latency
