#include "quant/market/microstructure.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <iterator>
#include <map>
#include <stdexcept>

namespace quant::microstructure {
namespace {

void require_finite(const double value, const char* name) {
  if (!std::isfinite(value)) {
    throw std::invalid_argument(std::string(name) + " must be finite");
  }
}

void validate_book_row(const double bid_price, const double bid_size,
                       const double ask_price, const double ask_size) {
  require_finite(bid_price, "bid_price");
  require_finite(bid_size, "bid_size");
  require_finite(ask_price, "ask_price");
  require_finite(ask_size, "ask_size");
  if (bid_price <= 0.0 || ask_price <= bid_price) {
    throw std::invalid_argument("book prices must satisfy 0 < bid < ask");
  }
  if (bid_size < 0.0 || ask_size < 0.0) {
    throw std::invalid_argument("book sizes must be non-negative");
  }
}

}  // namespace

std::vector<double> order_flow_imbalance(
    const double* bid_price, const double* bid_size,
    const double* ask_price, const double* ask_size,
    const std::uint64_t count) {
  if (count > 0 && (!bid_price || !bid_size || !ask_price || !ask_size)) {
    throw std::invalid_argument("book arrays must not be null when count > 0");
  }

  std::vector<double> result(static_cast<std::size_t>(count), 0.0);
  if (count == 0) return result;

  validate_book_row(bid_price[0], bid_size[0], ask_price[0], ask_size[0]);
  for (std::uint64_t i = 1; i < count; ++i) {
    validate_book_row(bid_price[i], bid_size[i], ask_price[i], ask_size[i]);
    const auto j = static_cast<std::size_t>(i);
    const auto p = j - 1;

    const double bid_flow =
        (bid_price[j] > bid_price[p]) ? bid_size[j] :
        (bid_price[j] < bid_price[p]) ? -bid_size[p] :
                                        bid_size[j] - bid_size[p];

    const double ask_flow =
        (ask_price[j] < ask_price[p]) ? -ask_size[j] :
        (ask_price[j] > ask_price[p]) ? ask_size[p] :
                                        ask_size[p] - ask_size[j];

    result[j] = bid_flow + ask_flow;
    if (!std::isfinite(result[j])) {
      throw std::overflow_error("OFI result is not finite");
    }
  }
  return result;
}

std::vector<SweepResult> detect_liquidity_sweeps(
    const double* high, const double* low, const double* close,
    const std::uint64_t count, const double pool_price) {
  require_finite(pool_price, "pool_price");
  if (pool_price <= 0.0) {
    throw std::invalid_argument("pool_price must be positive");
  }
  if (count > 0 && (!high || !low || !close)) {
    throw std::invalid_argument("OHLC arrays must not be null when count > 0");
  }

  std::vector<SweepResult> result(static_cast<std::size_t>(count));
  for (std::uint64_t i = 0; i < count; ++i) {
    const auto j = static_cast<std::size_t>(i);
    require_finite(high[j], "high");
    require_finite(low[j], "low");
    require_finite(close[j], "close");
    if (high[j] < low[j] || close[j] < low[j] || close[j] > high[j]) {
      throw std::invalid_argument("each bar must satisfy low <= close <= high");
    }
    result[j] = SweepResult{
        static_cast<std::uint8_t>(high[j] > pool_price && close[j] < pool_price),
        static_cast<std::uint8_t>(low[j] < pool_price && close[j] > pool_price)};
  }
  return result;
}

VolumeProfileSummary volume_profile_summary(
    const double* prices, const double* volumes, const std::uint64_t count,
    const double tick_size, const double value_area_fraction) {
  require_finite(tick_size, "tick_size");
  require_finite(value_area_fraction, "value_area_fraction");
  if (tick_size <= 0.0) throw std::invalid_argument("tick_size must be positive");
  if (value_area_fraction <= 0.0 || value_area_fraction > 1.0) {
    throw std::invalid_argument("value_area_fraction must be in (0, 1]");
  }
  if (count == 0 || !prices || !volumes) {
    throw std::invalid_argument("price and volume arrays must be non-empty");
  }

  std::map<std::int64_t, double> bins;
  double total = 0.0;
  for (std::uint64_t i = 0; i < count; ++i) {
    const auto j = static_cast<std::size_t>(i);
    require_finite(prices[j], "price");
    require_finite(volumes[j], "volume");
    if (prices[j] <= 0.0 || volumes[j] < 0.0) {
      throw std::invalid_argument("prices must be positive and volumes non-negative");
    }
    const long double quotient =
        static_cast<long double>(prices[j]) / static_cast<long double>(tick_size);
    const long double nearest = std::round(quotient);
    const long double tolerance =
        8.0L * static_cast<long double>(std::numeric_limits<double>::epsilon()) *
        std::max(1.0L, std::fabs(quotient));
    // Snap values that are only a floating-point representation error away
    // from a valid tick; otherwise preserve floor-based binning.
    const long double raw_bin =
        std::fabs(quotient - nearest) <= tolerance ? nearest : std::floor(quotient);
    if (!std::isfinite(raw_bin) ||
        raw_bin < static_cast<long double>(std::numeric_limits<std::int64_t>::min()) ||
        raw_bin > static_cast<long double>(std::numeric_limits<std::int64_t>::max())) {
      throw std::invalid_argument("price/tick_size bin index is out of range");
    }
    bins[static_cast<std::int64_t>(raw_bin)] += volumes[j];
    total += volumes[j];
    if (!std::isfinite(total)) throw std::overflow_error("total volume overflow");
  }
  if (total <= 0.0) throw std::invalid_argument("total volume must be positive");

  auto poc = bins.begin();
  for (auto it = bins.begin(); it != bins.end(); ++it) {
    if (it->second > poc->second) poc = it;  // stable low-price tie break
  }

  auto left = poc;
  auto right = poc;
  double accumulated = poc->second;
  const double target = total * value_area_fraction;
  while (accumulated < target && (left != bins.begin() || std::next(right) != bins.end())) {
    const bool has_left = left != bins.begin();
    const auto next_right = std::next(right);
    const bool has_right = next_right != bins.end();
    if (!has_left) {
      right = next_right;
      accumulated += right->second;
    } else if (!has_right) {
      --left;
      accumulated += left->second;
    } else {
      const auto prev_left = std::prev(left);
      if (prev_left->second >= next_right->second) {
        left = prev_left;  // ties expand to lower-price side
        accumulated += left->second;
      } else {
        right = next_right;
        accumulated += right->second;
      }
    }
  }

  return VolumeProfileSummary{
      static_cast<double>(poc->first) * tick_size,
      static_cast<double>(left->first) * tick_size,
      static_cast<double>(right->first) * tick_size,
      total,
      static_cast<std::uint64_t>(bins.size())};
}

}  // namespace quant::microstructure
