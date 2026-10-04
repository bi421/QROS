#ifndef QROS_LOW_LATENCY_CANDLE_GEOMETRY_H
#define QROS_LOW_LATENCY_CANDLE_GEOMETRY_H
#include <cstddef>
namespace quant::low_latency {
class CandleGeometryKernel final {
public:
  // Writes five values per candle: range, body_ratio, upper_wick_ratio,
  // lower_wick_ratio, close_position.
  static void compute(const double* open, const double* high, const double* low,
                      const double* close, std::size_t n, double* out);
};
}  // namespace quant::low_latency
#endif
