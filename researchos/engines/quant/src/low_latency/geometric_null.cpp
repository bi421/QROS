#include "quant/low_latency/geometric_null.h"

#include <cmath>
#include <stdexcept>

namespace quant::low_latency {

namespace {
void validate_common(const double* low, const double* high, std::size_t n,
                     const double* p1, const double* p2, double* out) {
  if (n == 0) return;
  if (!low || !high || !p1 || !p2 || !out) {
    throw std::invalid_argument("GeometricNull received a null buffer");
  }
}
}  // namespace

void GeometricNullKernel::interval_probability(const double* low, const double* high,
                                               const double* p1, const double* p2,
                                               std::size_t n, double* out) {
  validate_common(low, high, n, p1, p2, out);
  for (std::size_t i = 0; i < n; ++i) {
    const double range = high[i] - low[i];
    if (!std::isfinite(range) || !(range > 0.0) ||
        !std::isfinite(p1[i]) || !std::isfinite(p2[i]) ||
        p1[i] < low[i] || p2[i] > high[i] || p2[i] < p1[i]) {
      throw std::invalid_argument("invalid interval geometry");
    }
    out[i] = (p2[i] - p1[i]) / range;
  }
}

void GeometricNullKernel::first_passage(const double* open, const double* high,
                                        const double* low, std::size_t n,
                                        double* hit_high, double* hit_low) {
  if (n == 0) return;
  if (!open || !high || !low || !hit_high || !hit_low) {
    throw std::invalid_argument("GeometricNull received a null buffer");
  }
  for (std::size_t i = 0; i < n; ++i) {
    const double range = high[i] - low[i];
    if (!std::isfinite(open[i]) || !std::isfinite(high[i]) ||
        !std::isfinite(low[i]) || !(range > 0.0) ||
        open[i] < low[i] || open[i] > high[i]) {
      throw std::invalid_argument("invalid first-passage geometry");
    }
    hit_high[i] = (open[i] - low[i]) / range;
    hit_low[i] = (high[i] - open[i]) / range;
  }
}

}  // namespace quant::low_latency
