#include <gtest/gtest.h>

#include "quant/market/latency.h"

#include <cstdint>
#include <limits>
#include <stdexcept>
#include <vector>

using quant::microstructure::ExecutionPenalty;
using quant::microstructure::LatencyBreakdown;
using quant::microstructure::estimate_execution_penalty;
using quant::microstructure::observed_feed_latency_ns;
using quant::microstructure::project_price_after_latency;
using quant::microstructure::project_price_by_velocity_integral;
using quant::microstructure::total_latency_ns;

TEST(LatencyModel, SumsMeasuredComponents) {
  EXPECT_EQ(total_latency_ns(LatencyBreakdown{100, 20, 30, 50}), 200U);
}

TEST(LatencyModel, RejectsComponentOverflow) {
  EXPECT_THROW(total_latency_ns(LatencyBreakdown{
      std::numeric_limits<std::uint64_t>::max(), 1, 0, 0}), std::overflow_error);
}

TEST(LatencyModel, FeedLatencyRequiresMonotonicSynchronizedClocks) {
  EXPECT_EQ(observed_feed_latency_ns(1'000, 1'250), 250U);
  EXPECT_THROW(observed_feed_latency_ns(1'250, 1'000), std::invalid_argument);
}

TEST(LatencyModel, IntegratesMeasuredVelocitySamplesAcrossLatency) {
  // Integral of linearly sampled velocity: trapezoids give 0.5*(2+4)*1
  // + 0.5*(4+6)*1 = 8 price units. Add the explicit residual 0.25.
  EXPECT_NEAR(project_price_by_velocity_integral(
                  2'000.0, std::vector<double>{0.0, 1.0, 2.0},
                  std::vector<double>{2.0, 4.0, 6.0}, 0.25),
              2'008.25, 1e-12);
}

TEST(LatencyModel, VelocityIntegralRejectsMalformedSamples) {
  EXPECT_THROW(project_price_by_velocity_integral(
      2'000.0, std::vector<double>{0.0, 1.0},
      std::vector<double>{2.0}, 0.0), std::invalid_argument);
  EXPECT_THROW(project_price_by_velocity_integral(
      2'000.0, std::vector<double>{0.0, 0.0},
      std::vector<double>{2.0, 4.0}, 0.0), std::invalid_argument);
  EXPECT_THROW(project_price_by_velocity_integral(
      2'000.0, std::vector<double>{0.1, 1.0},
      std::vector<double>{2.0, 4.0}, 0.0), std::invalid_argument);
}

TEST(LatencyModel, ProjectsPriceUsingDriftAndExplicitResidual) {
  // 250 ms * 2.0 price-units/second + 0.1 scenario residual.
  EXPECT_NEAR(project_price_after_latency(2'000.0, 2.0, 250'000'000, 0.1),
              2'000.6, 1e-12);
}

TEST(LatencyModel, PenaltyCombinesDriftDiffusionAndParticipationImpact) {
  const ExecutionPenalty result = estimate_execution_penalty(
      1'000'000'000,  // one second
      2.0,            // price units / sqrt(second)
      0.5,            // price units / second
      10.0,           // order size
      100.0,          // available liquidity
      3.0);           // price units per participation ratio

  EXPECT_DOUBLE_EQ(result.elapsed_seconds, 1.0);
  EXPECT_DOUBLE_EQ(result.expected_drift_price, 0.5);
  EXPECT_NEAR(result.expected_diffusion_abs_price, 2.0 * 0.7978845608028654, 1e-12);
  EXPECT_DOUBLE_EQ(result.expected_market_impact_price, 0.3);
  EXPECT_NEAR(result.expected_total_price, 0.5 + 2.0 * 0.7978845608028654 + 0.3, 1e-12);
  EXPECT_DOUBLE_EQ(result.order_to_liquidity_ratio, 0.1);
}

TEST(LatencyModel, RejectsInvalidLiquidityAndVolatility) {
  EXPECT_THROW(estimate_execution_penalty(1, -1.0, 0.0, 1.0, 10.0, 1.0),
               std::invalid_argument);
  EXPECT_THROW(estimate_execution_penalty(1, 1.0, 0.0, 1.0, 0.0, 1.0),
               std::invalid_argument);
}
