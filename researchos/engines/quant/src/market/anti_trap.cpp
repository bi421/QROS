#include "quant/market/anti_trap.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace quant::microstructure {
namespace {

void require_finite(double value, const char* name) {
  if (!std::isfinite(value)) {
    throw std::invalid_argument(name);
  }
}

}  // namespace

AntiTrapResult evaluate_anti_trap(const AntiTrapInput& input) {
  require_finite(input.open, "open must be finite");
  require_finite(input.high, "high must be finite");
  require_finite(input.low, "low must be finite");
  require_finite(input.close, "close must be finite");
  require_finite(input.prior_range_high, "prior_range_high must be finite");
  require_finite(input.prior_range_low, "prior_range_low must be finite");
  require_finite(input.atr, "atr must be finite");
  require_finite(input.spread_price, "spread_price must be finite");
  require_finite(input.max_spread_price, "max_spread_price must be finite");
  require_finite(input.estimated_slippage_price, "estimated_slippage_price must be finite");
  require_finite(input.max_slippage_price, "max_slippage_price must be finite");
  require_finite(input.max_impulse_atr, "max_impulse_atr must be finite");

  if (input.atr <= 0.0 || input.high < input.low ||
      input.high < std::max(input.open, input.close) ||
      input.low > std::min(input.open, input.close) ||
      input.prior_range_high <= input.prior_range_low ||
      input.spread_price < 0.0 || input.max_spread_price < 0.0 ||
      input.estimated_slippage_price < 0.0 || input.max_slippage_price < 0.0 ||
      input.max_impulse_atr <= 0.0) {
    throw std::invalid_argument("invalid OHLC, range, ATR, spread, slippage or threshold");
  }

  const double candle_range = input.high - input.low;
  const double upper_wick = input.high - std::max(input.open, input.close);
  const double lower_wick = std::min(input.open, input.close) - input.low;
  const double impulse = std::abs(input.close - input.open) / input.atr;

  AntiTrapResult result{};
  result.impulse_atr = impulse;
  if (candle_range > 0.0) {
    result.upper_wick_fraction = upper_wick / candle_range;
    result.lower_wick_fraction = lower_wick / candle_range;
  }

  const bool upward_sweep_rejected =
      input.high > input.prior_range_high && input.close <= input.prior_range_high;
  const bool downward_sweep_rejected =
      input.low < input.prior_range_low && input.close >= input.prior_range_low;
  if (upward_sweep_rejected) {
    result.upward_sweep_atr = (input.high - input.prior_range_high) / input.atr;
    result.reason_mask |= kAntiTrapUpwardSweepRejected;
  }
  if (downward_sweep_rejected) {
    result.downward_sweep_atr = (input.prior_range_low - input.low) / input.atr;
    result.reason_mask |= kAntiTrapDownwardSweepRejected;
  }

  if (input.signal_age_ns > input.max_signal_age_ns) {
    result.reason_mask |= kAntiTrapStaleSignal;
  }
  if (input.spread_price > input.max_spread_price) {
    result.reason_mask |= kAntiTrapSpreadTooWide;
  }
  if (input.estimated_slippage_price > input.max_slippage_price) {
    result.reason_mask |= kAntiTrapSlippageTooHigh;
  }
  if (impulse > input.max_impulse_atr) {
    result.reason_mask |= kAntiTrapImpulseChase;
  }

  const std::uint32_t global_blocks =
      kAntiTrapStaleSignal | kAntiTrapSpreadTooWide |
      kAntiTrapSlippageTooHigh | kAntiTrapImpulseChase;
  const bool globally_eligible = (result.reason_mask & global_blocks) == 0;
  result.allow_long = globally_eligible && !upward_sweep_rejected;
  result.allow_short = globally_eligible && !downward_sweep_rejected;
  return result;
}

}  // namespace quant::microstructure
