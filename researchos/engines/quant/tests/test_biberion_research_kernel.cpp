#include <gtest/gtest.h>

#include "quant/biberion/research_kernel.h"

#include <vector>

using namespace quant::biberion;

TEST(BiberionVolumeSurge, UsesOnlyPriorWindow) {
  VolumeSurge detector(3, 1.0);
  EXPECT_FALSE(detector.observe(10.0));
  EXPECT_FALSE(detector.observe(10.0));
  EXPECT_FALSE(detector.observe(10.0));
  EXPECT_TRUE(detector.observe(100.0));
  EXPECT_DOUBLE_EQ(detector.threshold(), 10.0);
}

TEST(BiberionSignals, SidelineLockdownAlwaysBlocksCross) {
  std::vector<double> closes(25, 100.0);
  closes.push_back(200.0);
  const auto signal = evaluate_cross(closes, {100.0, 101.0}, 5, 25, true, true);
  EXPECT_FALSE(signal.approved);
  EXPECT_EQ(signal.reason, "sideline_lockdown");
}

TEST(BiberionSignals, RequiresVolumeAndBenchmarkAlignment) {
  std::vector<double> closes(25, 100.0);
  closes.push_back(200.0);
  const auto no_volume = evaluate_cross(closes, {100.0, 101.0}, 5, 25, false, false);
  EXPECT_FALSE(no_volume.approved);
  EXPECT_EQ(no_volume.reason, "volume_not_confirmed");
  const auto aligned = evaluate_cross(closes, {100.0, 101.0}, 5, 25, true, false);
  EXPECT_TRUE(aligned.approved);
  EXPECT_EQ(aligned.direction, 1);
}

TEST(BiberionRisk, RejectsAssetExposureOverCap) {
  BasketLimits limits;
  limits.equity = 100000.0;
  BasketProposal proposal{"A", 100.0, 99.0, 2000.0};
  const auto decision = approve_cash_basket(limits, {proposal});
  EXPECT_FALSE(decision.approved);
  EXPECT_EQ(decision.reason, "asset_allocation_or_stop_risk_exceeded");
}

TEST(BiberionRisk, AcceptsBoundedCashBasket) {
  BasketLimits limits;
  limits.equity = 100000.0;
  BasketProposal proposal{"A", 100.0, 99.0, 1000.0};
  const auto decision = approve_cash_basket(limits, {proposal});
  EXPECT_TRUE(decision.approved);
  EXPECT_DOUBLE_EQ(decision.total_notional, 1000.0);
  EXPECT_DOUBLE_EQ(decision.planned_loss, 10.0);
}
