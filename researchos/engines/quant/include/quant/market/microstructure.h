#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace quant::microstructure {

// UTC epoch nanoseconds from the source clock and local UTC receipt clock.
// Keep both values: event time is for market ordering; ingest time is for
// observability/replay of information availability. Never silently overwrite
// one with the other. Clock skew can make ingest_time_ns < event_time_ns.
enum class MarketEventKind : std::uint8_t {
  Trade = 0,
  Quote = 1,
  BookSnapshot = 2,
  BookDelta = 3,
};

struct TimedMarketEvent {
  std::string symbol{"XAUUSD"};
  std::string source_id{};
  std::string venue{};
  MarketEventKind kind{MarketEventKind::Trade};
  std::uint64_t sequence{0};
  std::int64_t event_time_ns{0};
  std::int64_t ingest_time_ns{0};
  double price{0.0};
  double size{0.0};
  std::int8_t aggressor_side{0};  // -1 sell, 0 unknown, +1 buy
};

struct SweepResult {
  std::uint8_t swept_above{0};
  std::uint8_t swept_below{0};
};

struct VolumeProfileSummary {
  double poc_price{0.0};
  double value_area_low{0.0};
  double value_area_high{0.0};
  double total_volume{0.0};
  std::uint64_t occupied_bins{0};
};

// Cont-style top-of-book order-flow imbalance, one output per snapshot.
// All spans/arrays must have identical length and valid finite values.
// First observation has OFI=0 because no prior book state exists.
std::vector<double> order_flow_imbalance(
    const double* bid_price, const double* bid_size,
    const double* ask_price, const double* ask_size,
    std::uint64_t count);

// Detect a sweep of a pre-identified liquidity pool. A sweep above means
// high > pool and close < pool; below means low < pool and close > pool.
// Strict inequalities are intentional and deterministic.
std::vector<SweepResult> detect_liquidity_sweeps(
    const double* high, const double* low, const double* close,
    std::uint64_t count, double pool_price);

// Deterministic volume-at-price profile. Prices are assigned to bins by
// floor(price / tick_size); ties for POC choose the lowest price bin.
// Value area expands from POC toward the larger adjacent volume; exact ties
// choose the lower-price side. The target fraction must be in (0, 1].
VolumeProfileSummary volume_profile_summary(
    const double* prices, const double* volumes,
    std::uint64_t count, double tick_size,
    double value_area_fraction = 0.70);

}  // namespace quant::microstructure
