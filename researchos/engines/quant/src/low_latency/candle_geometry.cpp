#include "quant/low_latency/candle_geometry.h"

#include <cmath>
#include <stdexcept>

namespace quant::low_latency {

void CandleGeometryKernel::compute(const double* open, const double* high,
                                   const double* low, const double* close,
                                   std::size_t n, CandleGeometry* out) {
  if (n == 0) return;
  if (!open || !high || !low || !close || !out) {
    throw std::invalid_argument("CandleGeometry received a null buffer");
  }

  for (std::size_t i = 0; i < n; ++i) {
    const double h = high[i];
    const double l = low[i];
    const double r = h - l;
    if (!(std::isfinite(open[i]) && std::isfinite(h) &&
          std::isfinite(l) && std::isfinite(close[i])) || !(r > 0.0)) {
      throw std::invalid_argument("OHLC contains non-finite values or non-positive range");
    }
    if (open[i] < l || open[i] > h || close[i] < l || close[i] > h) {
      throw std::invalid_argument("Open/Close must lie within High/Low");
    }

    const double upper = h - (open[i] > close[i] ? open[i] : close[i]);
    const double lower = (open[i] < close[i] ? open[i] : close[i]) - l;
    out[i] = CandleGeometry{
        r,
        std::abs(close[i] - open[i]) / r,
        upper / r,
        lower / r,
        (close[i] - l) / r,
    };
  }
}

}  // namespace quant::low_latency
