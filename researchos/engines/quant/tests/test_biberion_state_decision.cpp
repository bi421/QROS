#include <gtest/gtest.h>

#include "quant/biberion/research_kernel.h"

#include <vector>

using namespace quant::biberion;

TEST(BiberionStateDecision, SoftmaxProducesNormalizedBullishState) {
  StateModel model;
  model.weights = std::vector<double>(18, 0.0);
  model.bias = {0.0, 0.0, 3.0};
  model.threshold = 0.75;
  SafetyObservation observation{20.0, 15.0, 0.2, true};
  SafetyLimits limits;
  const auto result = evaluate_market_state(std::vector<double>(6, 0.0), observation, model, limits);
  EXPECT_TRUE(result.safety_passed);
  EXPECT_EQ(result.state, 1);
  EXPECT_GT(result.p_bullish, 0.75);
  EXPECT_NEAR(result.p_bearish + result.p_neutral + result.p_bullish, 1.0, 1e-12);
}

TEST(BiberionStateDecision, SafetyGateForcesNeutralDespiteHighProbability) {
  StateModel model;
  model.weights = std::vector<double>(18, 0.0);
  model.bias = {0.0, 0.0, 5.0};
  SafetyObservation observation{500.0, 15.0, 0.2, true};
  SafetyLimits limits;
  const auto result = evaluate_market_state(std::vector<double>(6, 0.0), observation, model, limits);
  EXPECT_FALSE(result.safety_passed);
  EXPECT_EQ(result.state, 0);
  EXPECT_EQ(result.reason, "safety_gate_latency_exceeded");
  EXPECT_GT(result.p_bullish, 0.75);
}

TEST(BiberionStateDecision, RejectsMalformedFeatureShape) {
  StateModel model;
  model.weights = std::vector<double>(18, 0.0);
  model.bias = {0.0, 0.0, 0.0};
  SafetyObservation observation{20.0, 15.0, 0.2, true};
  SafetyLimits limits;
  const auto result = evaluate_market_state({0.0, 0.0}, observation, model, limits);
  EXPECT_EQ(result.state, 0);
  EXPECT_FALSE(result.safety_passed);
  EXPECT_EQ(result.reason, "invalid_model_features_or_safety_inputs");
}
