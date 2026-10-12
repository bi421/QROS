#include <gtest/gtest.h>

#include "quant/market/microstructure.h"

#include <array>
#include <stdexcept>

using quant::microstructure::detect_liquidity_sweeps;
using quant::microstructure::order_flow_imbalance;
using quant::microstructure::volume_profile_summary;

TEST(MicrostructureKernel, OfiUsesPriorBookAndIsDeterministic) {
  const std::array<double, 3> bid_price{100.0, 100.0, 100.1};
  const std::array<double, 3> bid_size{10.0, 12.0, 11.0};
  const std::array<double, 3> ask_price{100.2, 100.2, 100.3};
  const std::array<double, 3> ask_size{9.0, 8.0, 7.0};

  const auto result = order_flow_imbalance(
      bid_price.data(), bid_size.data(), ask_price.data(), ask_size.data(), bid_price.size());

  ASSERT_EQ(result.size(), 3U);
  EXPECT_DOUBLE_EQ(result[0], 0.0);
  EXPECT_DOUBLE_EQ(result[1], 3.0);
  EXPECT_DOUBLE_EQ(result[2], 11.0);
}

TEST(MicrostructureKernel, RejectsCrossedOrInvalidBook) {
  const std::array<double, 1> bid_price{100.2};
  const std::array<double, 1> bid_size{1.0};
  const std::array<double, 1> ask_price{100.1};
  const std::array<double, 1> ask_size{1.0};
  EXPECT_THROW(order_flow_imbalance(
      bid_price.data(), bid_size.data(), ask_price.data(), ask_size.data(), 1),
      std::invalid_argument);
}

TEST(MicrostructureKernel, DetectsSweepsAroundKnownPool) {
  const std::array<double, 3> high{101.0, 100.5, 100.5};
  const std::array<double, 3> low{99.5, 98.0, 99.5};
  const std::array<double, 3> close{99.8, 100.2, 100.0};
  const auto result = detect_liquidity_sweeps(
      high.data(), low.data(), close.data(), high.size(), 100.0);

  ASSERT_EQ(result.size(), 3U);
  EXPECT_EQ(result[0].swept_above, 1U);
  EXPECT_EQ(result[0].swept_below, 0U);
  EXPECT_EQ(result[1].swept_above, 0U);
  EXPECT_EQ(result[1].swept_below, 1U);
  EXPECT_EQ(result[2].swept_above, 0U);
  EXPECT_EQ(result[2].swept_below, 0U);
}

TEST(MicrostructureKernel, BuildsDeterministicPocAndValueArea) {
  const std::array<double, 4> prices{100.0, 100.0, 101.0, 102.0};
  const std::array<double, 4> volumes{2.0, 3.0, 4.0, 1.0};
  const auto result = volume_profile_summary(
      prices.data(), volumes.data(), prices.size(), 1.0, 0.70);

  EXPECT_DOUBLE_EQ(result.poc_price, 100.0);
  EXPECT_DOUBLE_EQ(result.value_area_low, 100.0);
  EXPECT_DOUBLE_EQ(result.value_area_high, 101.0);
  EXPECT_DOUBLE_EQ(result.total_volume, 10.0);
  EXPECT_EQ(result.occupied_bins, 3U);
}

TEST(MicrostructureKernel, RejectsZeroTotalVolume) {
  const std::array<double, 1> prices{100.0};
  const std::array<double, 1> volumes{0.0};
  EXPECT_THROW(volume_profile_summary(
      prices.data(), volumes.data(), prices.size(), 1.0, 0.70),
      std::invalid_argument);
}
