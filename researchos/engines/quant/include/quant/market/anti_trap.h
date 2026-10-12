#pragma once

#include <cstdint>

namespace quant::microstructure {

// Deterministic evidence filter for stale data, impulse chasing and
// level-rejection patterns. It detects candle geometry, not intent or spoofing.
struct AntiTrapInput {
  double open{0.0};
  double high{0.0};
  double low{0.0};
  double close{0.0};
  double prior_range_high{0.0};
  double prior_range_low{0.0};
  double atr{0.0};
  double spread_price{0.0};
  double max_spread_price{0.0};
  double estimated_slippage_price{0.0};
  double max_slippage_price{0.0};
  std::uint64_t signal_age_ns{0};
  std::uint64_t max_signal_age_ns{0};
  double max_impulse_atr{2.0};
};

enum AntiTrapReason : std::uint32_t {
  kAntiTrapNone = 0,
  kAntiTrapStaleSignal = 1U << 0,
  kAntiTrapSpreadTooWide = 1U << 1,
  kAntiTrapSlippageTooHigh = 1U << 2,
  kAntiTrapImpulseChase = 1U << 3,
  kAntiTrapUpwardSweepRejected = 1U << 4,
  kAntiTrapDownwardSweepRejected = 1U << 5,
};

struct AntiTrapResult {
  bool allow_long{false};
  bool allow_short{false};
  std::uint32_t reason_mask{kAntiTrapNone};
  double impulse_atr{0.0};
  double upper_wick_fraction{0.0};
  double lower_wick_fraction{0.0};
  double upward_sweep_atr{0.0};
  double downward_sweep_atr{0.0};
};

// This is a conservative signal-quality gate, not a trade predictor.
// Thresholds must be selected on training data and evaluated out-of-sample.
AntiTrapResult evaluate_anti_trap(const AntiTrapInput& input);

}  // namespace quant::microstructure
