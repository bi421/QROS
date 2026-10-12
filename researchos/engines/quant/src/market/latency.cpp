#include "quant/market/latency.h"

#include <cmath>
#include <limits>
#include <stdexcept>

namespace quant::microstructure {
namespace {

void require_finite(double value, const char* name) {
  if (!std::isfinite(value)) {
    throw std::invalid_argument(std::string(name) + " must be finite");
  }
}

double seconds_from_ns(std::uint64_t latency_ns) {
  return static_cast<double>(latency_ns) / 1'000'000'000.0;
}

}  // namespace

std::uint64_t total_latency_ns(const LatencyBreakdown& latency) {
  std::uint64_t total = 0;
  for (const auto component : {latency.network_ns, latency.serialization_ns,
                               latency.queue_ns, latency.processing_ns}) {
    if (component > std::numeric_limits<std::uint64_t>::max() - total) {
      throw std::overflow_error("total latency nanoseconds overflow");
    }
    total += component;
  }
  return total;
}

std::uint64_t observed_feed_latency_ns(const std::int64_t event_time_ns,
                                       const std::int64_t ingest_time_ns) {
  if (event_time_ns < 0 || ingest_time_ns < 0) {
    throw std::invalid_argument("timestamps must be non-negative UTC epoch nanoseconds");
  }
  if (ingest_time_ns < event_time_ns) {
    throw std::invalid_argument(
        "ingest timestamp precedes event timestamp; check clock synchronization");
  }
  return static_cast<std::uint64_t>(ingest_time_ns - event_time_ns);
}

double project_price_after_latency(const double reference_price,
                                   const double drift_price_per_second,
                                   const std::uint64_t latency_ns,
                                   const double epsilon_price) {
  require_finite(reference_price, "reference_price");
  require_finite(drift_price_per_second, "drift_price_per_second");
  require_finite(epsilon_price, "epsilon_price");
  if (reference_price <= 0.0) {
    throw std::invalid_argument("reference_price must be positive");
  }
  const double projected = reference_price +
      drift_price_per_second * seconds_from_ns(latency_ns) + epsilon_price;
  if (!std::isfinite(projected) || projected <= 0.0) {
    throw std::overflow_error("projected price must be finite and positive");
  }
  return projected;
}

ExecutionPenalty estimate_execution_penalty(
    const std::uint64_t latency_ns,
    const double volatility_price_per_sqrt_second,
    const double drift_price_per_second,
    const double order_size,
    const double available_liquidity,
    const double impact_coefficient) {
  require_finite(volatility_price_per_sqrt_second, "volatility_price_per_sqrt_second");
  require_finite(drift_price_per_second, "drift_price_per_second");
  require_finite(order_size, "order_size");
  require_finite(available_liquidity, "available_liquidity");
  require_finite(impact_coefficient, "impact_coefficient");
  if (volatility_price_per_sqrt_second < 0.0 || order_size < 0.0 ||
      available_liquidity <= 0.0 || impact_coefficient < 0.0) {
    throw std::invalid_argument(
        "volatility, order size and impact must be non-negative; liquidity must be positive");
  }

  constexpr double kSqrtTwoOverPi = 0.79788456080286535588;
  const double elapsed = seconds_from_ns(latency_ns);
  const double ratio = order_size / available_liquidity;
  if (!std::isfinite(ratio)) {
    throw std::overflow_error("order-to-liquidity ratio overflow");
  }

  const double drift = std::abs(drift_price_per_second) * elapsed;
  const double diffusion = volatility_price_per_sqrt_second *
                           std::sqrt(elapsed) * kSqrtTwoOverPi;
  const double impact = impact_coefficient * ratio;
  const double total = drift + diffusion + impact;
  if (!std::isfinite(total)) {
    throw std::overflow_error("execution penalty overflow");
  }
  return ExecutionPenalty{elapsed, drift, diffusion, impact, total, ratio};
}

}  // namespace quant::microstructure
