#include "quant/parallel/research_wave.h"

#include <cmath>
#include <future>
#include <stdexcept>

namespace quant::parallel {

namespace {

void require_finite(const std::vector<double>& values) {
  for (double value : values) {
    if (!std::isfinite(value)) {
      throw std::invalid_argument("research wave input contains non-finite value");
    }
  }
}

double compute_mean(const std::vector<double>& values) {
  if (values.empty()) return 0.0;
  long double sum = 0.0L;
  for (double value : values) sum += value;
  return static_cast<double>(sum / static_cast<long double>(values.size()));
}

double compute_variance(const std::vector<double>& values) {
  if (values.size() < 2) return 0.0;

  // Welford's one-pass algorithm: numerically stable and independent of the
  // mean worker, so variance can execute concurrently with every other wave.
  long double mean = 0.0L;
  long double m2 = 0.0L;
  std::size_t count = 0;
  for (double value : values) {
    ++count;
    const long double x = static_cast<long double>(value);
    const long double delta = x - mean;
    mean += delta / static_cast<long double>(count);
    const long double delta2 = x - mean;
    m2 += delta * delta2;
  }
  return static_cast<double>(m2 / static_cast<long double>(count - 1));
}

double compute_slope(const std::vector<double>& values) {
  const std::size_t n = values.size();
  if (n < 2) return 0.0;

  // OLS slope for x = 0,1,...,n-1:
  // beta = sum((x-xbar)(y-ybar)) / sum((x-xbar)^2).
  const long double xbar = static_cast<long double>(n - 1) / 2.0L;
  long double numerator = 0.0L;
  long double denominator = 0.0L;
  for (std::size_t i = 0; i < n; ++i) {
    const long double dx = static_cast<long double>(i) - xbar;
    numerator += dx * static_cast<long double>(values[i]);
    denominator += dx * dx;
  }
  return denominator == 0.0L ? 0.0 : static_cast<double>(numerator / denominator);
}

double compute_positive_rate(const std::vector<double>& values) {
  if (values.empty()) return 0.0;
  std::size_t positive = 0;
  for (double value : values) {
    if (value > 0.0) ++positive;
  }
  return static_cast<double>(positive) / static_cast<double>(values.size());
}

}  // namespace

ResearchWaveResult run_research_wave(const std::vector<double>& values) {
  require_finite(values);

  // One immutable input snapshot is read by all workers. No worker mutates
  // shared state and no intermediate copy of the input vector is created.
  auto mean_future = std::async(std::launch::async, [&values] {
    return compute_mean(values);
  });

  auto slope_future = std::async(std::launch::async, [&values] {
    return compute_slope(values);
  });

  auto positive_rate_future = std::async(std::launch::async, [&values] {
    return compute_positive_rate(values);
  });

  auto variance_future = std::async(std::launch::async, [&values] {
    return compute_variance(values);
  });

  ResearchWaveResult result;
  result.mean = mean_future.get();
  result.variance = variance_future.get();
  result.standard_deviation = std::sqrt(result.variance);
  result.linear_slope = slope_future.get();
  result.positive_rate = positive_rate_future.get();
  result.sample_size = values.size();
  return result;
}

}  // namespace quant::parallel
