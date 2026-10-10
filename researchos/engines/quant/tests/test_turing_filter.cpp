#include <gtest/gtest.h>

#include "quant/low_latency/turing_filter.h"

#include <cmath>
#include <limits>

using namespace quant::low_latency;

namespace {

TuringFilterConfig base_config() {
  TuringFilterConfig c;
  c.max_spread = 1.0;
  c.min_total_depth = 10.0;
  c.min_trade_volume = 1.0;
  c.min_abs_imbalance = 0.20;
  c.min_persistence = 2;
  c.max_samples = 8;
  c.event_probability_h = 0.80;
  c.event_probability_not_h = 0.20;
  c.lower_deciban = -9.0;
  c.upper_deciban = 12.0;
  return c;
}

TuringFilterTick tick(std::int64_t ts, double bid_volume = 8.0,
                      double ask_volume = 2.0) {
  TuringFilterTick t;
  t.timestamp_ns = ts;
  t.bid = 100.0;
  t.ask = 100.5;
  t.bid_volume = bid_volume;
  t.ask_volume = ask_volume;
  t.trade_volume = 2.0;
  return t;
}

}  // namespace

TEST(TuringFilterTest, ThresholdMappingMatchesSprtFormula) {
  const auto thresholds =
      TuringFilterEngine::thresholds_from_error_rates(0.05, 0.10);

  EXPECT_NEAR(thresholds.lower_deciban, -9.777236052888478, 1e-12);
  EXPECT_NEAR(thresholds.upper_deciban, 12.552725051033061, 1e-12);
}

TEST(TuringFilterTest, EvidenceIsFiniteAndSigned) {
  const double positive =
      TuringFilterEngine::evidence_deciban(0.80, 0.20);
  const double negative =
      TuringFilterEngine::evidence_deciban(0.20, 0.80);

  EXPECT_NEAR(positive, 6.020599913279624, 1e-12);
  EXPECT_NEAR(negative, -6.020599913279624, 1e-12);
  EXPECT_TRUE(std::isnan(
      TuringFilterEngine::evidence_deciban(0.0, 0.5)));
}

TEST(TuringFilterTest, MandatoryAnchorsGateBeforeOdds) {
  auto config = base_config();
  TuringFilterEngine engine(config);

  EXPECT_EQ(engine.process(tick(1)), TuringFilterDecision::Drop);
  EXPECT_EQ(engine.state().samples, 0u);
  EXPECT_EQ(engine.state().persistence, 1u);

  // Breaking the directional crib resets the sequential evidence.
  EXPECT_EQ(engine.process(tick(2, 2.0, 8.0)),
            TuringFilterDecision::Drop);
  EXPECT_EQ(engine.state().samples, 0u);
  EXPECT_DOUBLE_EQ(engine.state().log_odds_deciban, 0.0);
}

TEST(TuringFilterTest, SequentialOddsAcceptsOnlyAfterAnchorsAndThreshold) {
  auto config = base_config();
  TuringFilterEngine engine(config);

  EXPECT_EQ(engine.process(tick(1)), TuringFilterDecision::Drop);
  EXPECT_EQ(engine.process(tick(2)), TuringFilterDecision::Continue);
  EXPECT_EQ(engine.state().samples, 1u);
  EXPECT_NEAR(engine.state().log_odds_deciban, 6.020599913279624, 1e-12);

  EXPECT_EQ(engine.process(tick(3)), TuringFilterDecision::Accept);
  EXPECT_GE(engine.state().log_odds_deciban, config.upper_deciban);

  // A terminal result cannot leak stale odds into the next sequence.
  EXPECT_EQ(engine.process(tick(4)), TuringFilterDecision::Drop);
  EXPECT_EQ(engine.state().samples, 0u);
}

TEST(TuringFilterTest, BrokenStructuralCribAbortsPriorSequence) {
  auto config = base_config();
  config.min_persistence = 1;
  TuringFilterEngine engine(config);

  EXPECT_EQ(engine.process(tick(1)), TuringFilterDecision::Continue);
  auto broken = tick(2);
  broken.ask = 102.0;
  EXPECT_EQ(engine.process(broken), TuringFilterDecision::Drop);
  EXPECT_FALSE(engine.state().has_previous);

  EXPECT_EQ(engine.process(tick(3)), TuringFilterDecision::Continue);
  EXPECT_EQ(engine.state().samples, 1u);
}

TEST(TuringFilterTest, ContradictoryEvidenceCanHitLowerBoundary) {
  auto config = base_config();
  config.min_persistence = 1;
  config.lower_deciban = -3.0;
  config.contradiction_probability_h = 0.10;
  config.contradiction_probability_not_h = 0.90;
  TuringFilterEngine engine(config);

  EXPECT_EQ(engine.process(tick(1)), TuringFilterDecision::Continue);

  // The hard directional crib remains valid, but its strength weakens.
  EXPECT_EQ(engine.process(tick(2, 6.0, 4.0)),
            TuringFilterDecision::Reject);
  EXPECT_LE(engine.state().log_odds_deciban, config.lower_deciban);
}

TEST(TuringFilterTest, NonMonotonicTimestampDrops) {
  auto config = base_config();
  config.min_persistence = 1;
  TuringFilterEngine engine(config);

  EXPECT_EQ(engine.process(tick(10)), TuringFilterDecision::Continue);
  EXPECT_EQ(engine.process(tick(10)), TuringFilterDecision::Drop);
  EXPECT_EQ(engine.state().samples, 0u);
}

TEST(TuringFilterTest, StructuralDropDoesNotResetTimestampWatermark) {
  auto config = base_config();
  config.min_persistence = 1;
  TuringFilterEngine engine(config);

  EXPECT_EQ(engine.process(tick(10)), TuringFilterDecision::Continue);
  auto broken = tick(20);
  broken.ask = 102.0;
  EXPECT_EQ(engine.process(broken), TuringFilterDecision::Drop);

  // The broken quote resets evidence, not the monotonic timestamp watermark.
  EXPECT_EQ(engine.process(tick(15)), TuringFilterDecision::Drop);
  EXPECT_EQ(engine.process(tick(21)), TuringFilterDecision::Continue);
}

TEST(TuringFilterTest, NonFiniteInputFailsClosed) {
  auto config = base_config();
  config.min_persistence = 1;
  TuringFilterEngine engine(config);

  auto bad = tick(1);
  bad.bid = std::numeric_limits<double>::quiet_NaN();

  EXPECT_EQ(engine.process(bad), TuringFilterDecision::Drop);
  EXPECT_EQ(engine.state().samples, 0u);
  EXPECT_DOUBLE_EQ(engine.state().log_odds_deciban, 0.0);
}

TEST(TuringFilterTest, MaximumSampleBoundHaltsSequence) {
  auto config = base_config();
  config.min_persistence = 1;
  config.max_samples = 2;
  config.upper_deciban = 100.0;
  TuringFilterEngine engine(config);

  EXPECT_EQ(engine.process(tick(1)), TuringFilterDecision::Continue);
  EXPECT_EQ(engine.process(tick(2)), TuringFilterDecision::Continue);
  EXPECT_EQ(engine.state().samples, 2u);

  EXPECT_EQ(engine.process(tick(3)), TuringFilterDecision::Reject);
  EXPECT_EQ(engine.state().last_decision, TuringFilterDecision::Reject);
}

TEST(TuringFilterTest, BatchProcessingIsAllocationFreeAtEngineLayer) {
  auto config = base_config();
  TuringFilterEngine engine(config);

  const TuringFilterTick ticks[] = {tick(1), tick(2), tick(3)};
  std::uint8_t decisions[3]{};

  EXPECT_EQ(engine.process_batch(ticks, 3, decisions), 3u);
  EXPECT_EQ(decisions[0],
            static_cast<std::uint8_t>(TuringFilterDecision::Drop));
  EXPECT_EQ(decisions[1],
            static_cast<std::uint8_t>(TuringFilterDecision::Continue));
  EXPECT_EQ(decisions[2],
            static_cast<std::uint8_t>(TuringFilterDecision::Accept));
}

TEST(TuringFilterTest, InvalidConfigRejects) {
  auto config = base_config();
  config.event_probability_h = 1.0;
  TuringFilterEngine engine(config);

  EXPECT_EQ(engine.process(tick(1)), TuringFilterDecision::Reject);
  EXPECT_EQ(engine.state().last_decision, TuringFilterDecision::Reject);
}
