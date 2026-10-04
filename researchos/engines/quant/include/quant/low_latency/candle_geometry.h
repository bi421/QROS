#ifndef QROS_LOW_LATENCY_CANDLE_GEOMETRY_H
#define QROS_LOW_LATENCY_CANDLE_GEOMETRY_H

#include <cstddef>

namespace quant::low_latency {

struct CandleGeometry final {
  double range;
  double body_ratio;
  double upper_wick_ratio;
  double lower_wick_ratio;
  double close_position;
};

class CandleGeometryKernel final {
public:
  static void compute(const double* open, const double* high, const double* low,
                      const double* close, std::size_t n, CandleGeometry* out);
};

}  // namespace quant::low_latency

#endif
