#pragma once

#include <cstdint>

namespace quant::microstructure {

struct LatencyBreakdown {
  std::uint64_t network_ns{0};
  std::uint64_t serialization_ns{0};
  std::uint64_t queue_ns{0};
  std::uint64_t processing_ns{0};
};

struct ExecutionPenalty {
  double elapsed_seconds{0.0};
  double expected_drift_price{0.0};
  double expected_diffusion_abs_price{0.0};
  double expected_market_impact_price{0.0};
  double expected_total_price{0.0};
  double order_to_liquidity_ratio{0.0};
};

// Sum measured component durations. Throws on uint64 overflow.
std::uint64_t total_latency_ns(const LatencyBreakdown& latency);

// Receipt minus source event timestamp. Both clocks must be synchronized UTC
// epoch clocks; negative values fail closed rather than being clamped.
std::uint64_t observed_feed_latency_ns(std::int64_t event_time_ns,
                                      std::int64_t ingest_time_ns);

// Deterministic drift projection over latency. epsilon_price is an explicit
// scenario residual, not an RNG draw or a claim to predict market noise.
double project_price_after_latency(double reference_price,
                                   double drift_price_per_second,
                                   std::uint64_t latency_ns,
                                   double epsilon_price = 0.0);

// Expected adverse price movement under a zero-mean Gaussian diffusion,
// plus absolute drift and linear participation impact. sigma is price/sqrt(s),
// impact_coefficient is price units per unit participation ratio. This is an
// expected price penalty, NOT a probability or a fill-price guarantee.
ExecutionPenalty estimate_execution_penalty(
    std::uint64_t latency_ns,
    double volatility_price_per_sqrt_second,
    double drift_price_per_second,
    double order_size,
    double available_liquidity,
    double impact_coefficient);

}  // namespace quant::microstructure
