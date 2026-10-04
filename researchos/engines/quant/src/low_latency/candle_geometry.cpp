#include "quant/low_latency/candle_geometry.h"
#include <cmath>
#include <stdexcept>
namespace quant::low_latency {
void CandleGeometryKernel::compute(const double* open, const double* high,
                                   const double* low, const double* close,
                                   std::size_t n, double* out) {
  if (n == 0) return;
  if (!open || !high || !low || !close || !out)
    throw std::invalid_argument("CandleGeometry received a null buffer");
  for (std::size_t i = 0; i < n; ++i) {
    const double o=open[i], h=high[i], l=low[i], c=close[i], r=h-l;
    if (!std::isfinite(o) || !std::isfinite(h) || !std::isfinite(l) ||
        !std::isfinite(c) || !(r > 0.0) || o < l || o > h || c < l || c > h)
      throw std::invalid_argument("invalid OHLC geometry");
    const double upper=h-(o>c?o:c), lower=(o<c?o:c)-l;
    const std::size_t j=i*5;
    out[j]=r;
    out[j+1]=std::abs(c-o)/r;
    out[j+2]=upper/r;
    out[j+3]=lower/r;
    out[j+4]=(c-l)/r;
  }
}
}  // namespace quant::low_latency
