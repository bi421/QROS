#include "quant/market/multivariate_probability.h"
#include <gtest/gtest.h>
#include <stdexcept>

using namespace quant::microstructure;

namespace {
MultivariateProbabilityInput fixture() {
  MultivariateProbabilityInput x;
  x.base_probability = 0.85;
  x.latency_ms = 5;
  x.vxy = 6.5;
  x.dxy = 101.2;
  x.dxy_baseline = 101.2;
  x.alpha_per_ms = 0.001;
  x.beta_per_vxy_unit = 0.002;
  x.gamma_per_dxy_point = 0.01;
  x.gate_threshold = 0.70;
  x.calibration_verified = true;
  return x;
}
}  // namespace

TEST(MultivariateProbability, ExplicitPenaltyTerms) {
  const auto result = evaluate_multivariate_probability(fixture());
  EXPECT_NEAR(result.latency_penalty, 0.005, 1e-12);
  EXPECT_NEAR(result.volatility_penalty, 0.013, 1e-12);
  EXPECT_NEAR(result.dollar_deviation_penalty, 0, 1e-12);
  EXPECT_NEAR(result.estimated_success_probability, 0.832, 1e-12);
  EXPECT_TRUE(result.research_gate_pass);
}

TEST(MultivariateProbability, StressInputsReduceScore) {
  auto x = fixture();
  x.latency_ms = 50;
  x.vxy = 14.5;
  x.dxy = 106.8;
  const auto result = evaluate_multivariate_probability(x);
  EXPECT_NEAR(result.estimated_success_probability, 0.715, 1e-12);
  EXPECT_LT(result.estimated_success_probability, 0.832);
}

TEST(MultivariateProbability, UnverifiedCalibrationKeepsGateClosed) {
  auto x = fixture();
  x.calibration_verified = false;
  EXPECT_FALSE(evaluate_multivariate_probability(x).research_gate_pass);
}

TEST(MultivariateProbability, BelowThresholdKeepsGateClosed) {
  auto x = fixture();
  x.alpha_per_ms = 0.03;
  const auto result = evaluate_multivariate_probability(x);
  EXPECT_LT(result.estimated_success_probability, x.gate_threshold);
  EXPECT_FALSE(result.research_gate_pass);
}

TEST(MultivariateProbability, InvalidInputsThrow) {
  auto x = fixture();
  x.latency_ms = -1;
  EXPECT_THROW(evaluate_multivariate_probability(x), std::invalid_argument);
  x = fixture();
  x.beta_per_vxy_unit = -0.1;
  EXPECT_THROW(evaluate_multivariate_probability(x), std::invalid_argument);
}
