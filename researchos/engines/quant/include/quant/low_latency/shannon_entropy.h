#ifndef QROS_LOW_LATENCY_SHANNON_ENTROPY_H
#define QROS_LOW_LATENCY_SHANNON_ENTROPY_H

#include <cstddef>

namespace quant::low_latency {

class ShannonEntropyKernel final {
public:
  // H = -sum(p_i * log(p_i)) for each row of a contiguous probability matrix.
  // Zero-probability bins contribute zero. Rows must sum to one within tolerance.
  static void entropy(const double* probabilities, std::size_t rows,
                      std::size_t bins, double* out);

  // Normalized entropy H/log(bins), in [0,1] for a valid distribution.
  static void normalized_entropy(const double* probabilities, std::size_t rows,
                                 std::size_t bins, double* out);
};

}  // namespace quant::low_latency

#endif
