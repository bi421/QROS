#include "quant/low_latency/shannon_entropy.h"

#include <cmath>
#include <stdexcept>

namespace quant::low_latency {
namespace {

constexpr double kProbabilityTolerance = 1e-10;

double compute_row_entropy(const double* row, std::size_t bins) {
  if (bins == 0) throw std::invalid_argument("entropy requires at least one bin");

  double sum = 0.0;
  double entropy = 0.0;
  for (std::size_t j = 0; j < bins; ++j) {
    const double p = row[j];
    if (!std::isfinite(p) || p < 0.0 || p > 1.0)
      throw std::invalid_argument("entropy probabilities must be finite and in [0,1]");
    sum += p;
    if (p > 0.0) entropy -= p * std::log(p);
  }

  if (std::abs(sum - 1.0) > kProbabilityTolerance)
    throw std::invalid_argument("entropy probability row must sum to one");
  return entropy;
}

}  // namespace

void ShannonEntropyKernel::entropy(const double* probabilities, std::size_t rows,
                                   std::size_t bins, double* out) {
  if (rows == 0) return;
  if (!probabilities || !out)
    throw std::invalid_argument("ShannonEntropy received a null buffer");
  for (std::size_t i = 0; i < rows; ++i)
    out[i] = compute_row_entropy(probabilities + i * bins, bins);
}

void ShannonEntropyKernel::normalized_entropy(
    const double* probabilities, std::size_t rows, std::size_t bins, double* out) {
  if (rows == 0) return;
  if (!probabilities || !out)
    throw std::invalid_argument("ShannonEntropy received a null buffer");
  if (bins < 2) {
    if (bins == 0) throw std::invalid_argument("entropy requires at least one bin");
    for (std::size_t i = 0; i < rows; ++i) {
      (void)compute_row_entropy(probabilities + i * bins, bins);
      out[i] = 0.0;
    }
    return;
  }

  const double log_bins = std::log(static_cast<double>(bins));
  for (std::size_t i = 0; i < rows; ++i)
    out[i] = compute_row_entropy(probabilities + i * bins, bins) / log_bins;
}

}  // namespace quant::low_latency
