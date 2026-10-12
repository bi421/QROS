#include "quant/market/market_state_4d.h"
#include <cmath>
#include <limits>
#include <stdexcept>

namespace quant::market_state_4d {
std::vector<DataPoint4D> build_points(DataPoint4DView input, double allowed_clock_skew_ms) {
  if (!std::isfinite(allowed_clock_skew_ms) || allowed_clock_skew_ms < 0.0)
    throw std::invalid_argument("allowed_clock_skew_ms must be finite and non-negative");
  if (input.count > 0 && (!input.price || !input.volume || !input.event_time_ns || !input.ingest_time_ns))
    throw std::invalid_argument("non-empty input requires all four contiguous arrays");
  std::vector<DataPoint4D> result;
  result.reserve(static_cast<std::size_t>(input.count));
  for (std::uint64_t i = 0; i < input.count; ++i) {
    const double price = input.price[i], volume = input.volume[i];
    const auto event = input.event_time_ns[i], ingest = input.ingest_time_ns[i];
    if (!std::isfinite(price) || price <= 0.0)
      throw std::invalid_argument("price must be finite and positive");
    if (!std::isfinite(volume) || volume < 0.0)
      throw std::invalid_argument("volume must be finite and non-negative");
    if (event <= 0 || ingest <= 0)
      throw std::invalid_argument("timestamps must be positive UTC epoch nanoseconds");
    const long double delta_ns = static_cast<long double>(ingest) - static_cast<long double>(event);
    const long double latency_ms = delta_ns / 1'000'000.0L;
    if (!std::isfinite(static_cast<double>(latency_ms)) ||
        latency_ms < -static_cast<long double>(allowed_clock_skew_ms))
      throw std::invalid_argument("negative latency exceeds allowed clock skew");
    result.push_back(DataPoint4D{price, volume, event, ingest, static_cast<double>(latency_ms)});
  }
  return result;
}
}  // namespace quant::market_state_4d
