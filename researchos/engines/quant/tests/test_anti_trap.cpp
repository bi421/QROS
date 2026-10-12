#include <gtest/gtest.h>

#include "quant/market/anti_trap.h"

#include <stdexcept>

using quant::microstructure::AntiTrapInput;
using quant::microstructure::evaluate_anti_trap;
using quant::microstructure::kAntiTrapImpulseChase;
using quant::microstructure::kAntiTrapSlippageTooHigh;
using quant::microstructure::kAntiTrapSpreadTooWide;
using quant::microstructure::kAntiTrapStaleSignal;
using quant::microstructure::kAntiTrapUpwardSweepRejected;

namespace {
AntiTrapInput BaseInput() {
  AntiTrapInput input{};
  input.open = 100.0;
  input.high = 101.0;
  input.low = 99.0;
  input.close = 100.5;
  input.prior_range_high = 100.8;
  input.prior_range_low = 98.5;
  input.atr = 1.0;
  input.spread_price = 0.1;
  input.max_spread_price = 0.3;
  input.estimated_slippage_price = 0.1;
  input.max_slippage_price = 0.4;
  input.signal_age_ns = 10;
  input.max_signal_age_ns = 100;
  input.max_impulse_atr = 2.0;
  return input;
}
}  // namespace

TEST(AntiTrapFilter, AllowsCleanFreshModerateCandle) {
  const auto result = evaluate_anti_trap(BaseInput());
  EXPECT_TRUE(result.allow_long);
  EXPECT_TRUE(result.allow_short);
  EXPECT_EQ(result.reason_mask, 0U);
}

TEST(AntiTrapFilter, BlocksLongAfterUpwardSweepAndCloseBackBelowLevel) {
  auto input = BaseInput();
  input.high = 102.0;
  input.close = 100.7;
  const auto result = evaluate_anti_trap(input);
  EXPECT_FALSE(result.allow_long);
  EXPECT_TRUE(result.allow_short);
  EXPECT_NE(result.reason_mask & kAntiTrapUpwardSweepRejected, 0U);
  EXPECT_NEAR(result.upward_sweep_atr, 1.2, 1e-12);
}

TEST(AntiTrapFilter, BlocksBothDirectionsWhenSignalIsStaleOrCostsAreHigh) {
  auto input = BaseInput();
  input.signal_age_ns = 101;
  input.spread_price = 0.31;
  input.estimated_slippage_price = 0.41;
  const auto result = evaluate_anti_trap(input);
  EXPECT_FALSE(result.allow_long);
  EXPECT_FALSE(result.allow_short);
  EXPECT_NE(result.reason_mask & kAntiTrapStaleSignal, 0U);
  EXPECT_NE(result.reason_mask & kAntiTrapSpreadTooWide, 0U);
  EXPECT_NE(result.reason_mask & kAntiTrapSlippageTooHigh, 0U);
}

TEST(AntiTrapFilter, BlocksImpulseChasing) {
  auto input = BaseInput();
  input.open = 100.0;
  input.close = 103.0;
  input.high = 103.2;
  const auto result = evaluate_anti_trap(input);
  EXPECT_FALSE(result.allow_long);
  EXPECT_FALSE(result.allow_short);
  EXPECT_NE(result.reason_mask & kAntiTrapImpulseChase, 0U);
  EXPECT_DOUBLE_EQ(result.impulse_atr, 3.0);
}

TEST(AntiTrapFilter, RejectsInvalidOhlcAndAtr) {
  auto input = BaseInput();
  input.high = 98.0;
  EXPECT_THROW(evaluate_anti_trap(input), std::invalid_argument);
  input = BaseInput();
  input.atr = 0.0;
  EXPECT_THROW(evaluate_anti_trap(input), std::invalid_argument);
}
