// Research Optimization Engine — comprehensive unit tests.
//
// Covers: parameter spaces (grids, ranges, int ranges, log scale, mixed-radix
// combo decoding, overflow), ParamSet accessors, optimization metrics
// (including the equity-curve stability score), grid/random/seeded search,
// deterministic ranking in both directions, top-N retention, parallel
// execution determinism, thread safety, error handling, result hashing, and
// the high-level ResearchRunner.

#include "quant/research/optimizer.h"
#include "quant/research/optimization_result.h"
#include "quant/research/parameter_space.h"
#include "quant/research/research_runner.h"

#include "quant/strategy/strategy_kernel.h"

#include <gtest/gtest.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <string>
#include <thread>
#include <unordered_set>
#include <vector>

using namespace quant;
using namespace quant::strategy;
using namespace quant::research;

namespace {

TimePoint tp(int64_t minute) {
  return TimePoint() + std::chrono::minutes(minute);
}

OHLCV mk(double o, double h, double l, double c, int64_t minute,
         double v = 1000.0) {
  OHLCV b;
  b.timestamp = tp(minute);
  b.open = o;
  b.high = h;
  b.low = l;
  b.close = c;
  b.volume = v;
  return b;
}

// Deterministic oscillating-with-trend series (produces multiple SMA crosses).
std::vector<OHLCV> make_bars(size_t n) {
  std::vector<OHLCV> bars;
  bars.reserve(n);
  for (size_t i = 0; i < n; ++i) {
    const double trend = 0.02 * static_cast<double>(i);
    const double wave = 5.0 * std::sin(static_cast<double>(i) * 0.15);
    const double close = 100.0 + trend + wave;
    const double open = i == 0 ? close : bars.back().close;
    bars.push_back(mk(open, std::max(open, close) + 0.5,
                      std::min(open, close) - 0.5, close,
                      static_cast<int64_t>(i)));
  }
  return bars;
}

strategy::StrategyConfig zero_cost() {
  strategy::StrategyConfig cfg;
  cfg.trade.commission_pct = 0.0;
  cfg.trade.spread_pct = 0.0;
  cfg.trade.slippage_pct = 0.0;
  cfg.trade.sizing = strategy::PositionSizing::FixedLot;
  cfg.trade.fixed_lot = 1.0;
  return cfg;
}

// Long when fast SMA crosses above slow SMA, close when it crosses below.
FunctionSignalGenerator sma_cross_gen() {
  return FunctionSignalGenerator([](const std::vector<OHLCV>& bars,
                                    const ParamSet& p) {
    const int fast = static_cast<int>(p.get_int("fast", 5));
    const int slow = static_cast<int>(p.get_int("slow", 20));
    const size_t n = bars.size();
    std::vector<double> f(n, 0.0), s(n, 0.0);
    for (size_t i = 0; i < n; ++i) {
      if (i + 1 >= static_cast<size_t>(fast)) {
        double sum = 0.0;
        for (size_t k = i + 1 - static_cast<size_t>(fast); k <= i; ++k)
          sum += bars[k].close;
        f[i] = sum / static_cast<double>(fast);
      }
      if (i + 1 >= static_cast<size_t>(slow)) {
        double sum = 0.0;
        for (size_t k = i + 1 - static_cast<size_t>(slow); k <= i; ++k)
          sum += bars[k].close;
        s[i] = sum / static_cast<double>(slow);
      }
    }
    std::vector<StrategySignal> sigs;
    bool in_long = false;
    for (size_t i = 1; i < n; ++i) {
      if (i + 1 < static_cast<size_t>(fast) ||
          i + 1 < static_cast<size_t>(slow))
        continue;
      const bool cross_up = f[i] > s[i] && f[i - 1] <= s[i - 1];
      const bool cross_dn = f[i] < s[i] && f[i - 1] >= s[i - 1];
      if (cross_up && !in_long) {
        StrategySignal sig;
        sig.bar_index = static_cast<int64_t>(i);
        sig.action = SignalAction::Open;
        sig.side = TradeSide::Long;
        sigs.push_back(sig);
        in_long = true;
      } else if (cross_dn && in_long) {
        StrategySignal sig;
        sig.bar_index = static_cast<int64_t>(i);
        sig.action = SignalAction::Close;
        sig.side = TradeSide::Long;
        sigs.push_back(sig);
        in_long = false;
      }
    }
    return sigs;
  });
}

// Long signal every `period` bars (uses only the `period` parameter).
FunctionSignalGenerator interval_gen() {
  return FunctionSignalGenerator([](const std::vector<OHLCV>& bars,
                                    const ParamSet& p) {
    const int64_t period = p.get_int("period", 5);
    std::vector<StrategySignal> sigs;
    for (int64_t i = 1; i + 1 < static_cast<int64_t>(bars.size());
         i += period) {
      StrategySignal sig;
      sig.bar_index = i;
      sig.action = SignalAction::Open;
      sig.side = TradeSide::Long;
      sigs.push_back(sig);
    }
    return sigs;
  });
}

// Maps `stop` and `tp` parameters onto the trade config.
const FunctionConfigProvider& stop_tp_provider() {
  static const FunctionConfigProvider provider([](const ParamSet& p) {
    strategy::StrategyConfig cfg = zero_cost();
    cfg.trade.stop_loss = p.get("stop", 2.0);
    cfg.trade.take_profit = p.get("tp", 4.0);
    return cfg;
  });
  return provider;
}

OptimizerConfig grid_cfg(OptimizationMetric metric = OptimizationMetric::NetProfit,
                         size_t top_n = 0, size_t threads = 1) {
  OptimizerConfig cfg;
  cfg.search_type = SearchType::Grid;
  cfg.rank_metric = metric;
  cfg.top_n = top_n;
  cfg.max_parallelism = threads;
  return cfg;
}

OptimizerConfig seeded_cfg(uint64_t seed, size_t samples,
                           OptimizationMetric metric = OptimizationMetric::NetProfit,
                           size_t threads = 1) {
  OptimizerConfig cfg;
  cfg.search_type = SearchType::Seeded;
  cfg.seed = seed;
  cfg.random_samples = samples;
  cfg.rank_metric = metric;
  cfg.max_parallelism = threads;
  return cfg;
}

} // namespace

// ── ParamSet ────────────────────────────────────────────────────────────────

TEST(ParamSet, DefaultEmpty) {
  ParamSet p;
  EXPECT_EQ(p.size(), 0u);
  EXPECT_FALSE(p.has("a"));
}

TEST(ParamSet, SetAndGet) {
  ParamSet p;
  p.set("stop", 2.5);
  EXPECT_TRUE(p.has("stop"));
  EXPECT_DOUBLE_EQ(p.get("stop"), 2.5);
}

TEST(ParamSet, GetFallbackWhenMissing) {
  ParamSet p;
  EXPECT_DOUBLE_EQ(p.get("missing", 7.0), 7.0);
  EXPECT_EQ(p.get_int("missing", 9), 9);
}

TEST(ParamSet, GetIntRoundsToNearest) {
  ParamSet p;
  p.set("a", 5.4);
  p.set("b", 5.6);
  EXPECT_EQ(p.get_int("a"), 5);
  EXPECT_EQ(p.get_int("b"), 6);
}

TEST(ParamSet, SetOverwritesExistingValue) {
  ParamSet p;
  p.set("x", 1.0);
  p.set("x", 2.0);
  EXPECT_EQ(p.size(), 1u);
  EXPECT_DOUBLE_EQ(p.get("x"), 2.0);
}

TEST(ParamSet, SizeReflectsParameterCount) {
  ParamSet p;
  EXPECT_EQ(p.size(), 0u);
  p.set("a", 1.0);
  p.set("b", 2.0);
  p.set("c", 3.0);
  EXPECT_EQ(p.size(), 3u);
}

TEST(ParamSet, NamesAndValuesAligned) {
  ParamSet p;
  p.set("fast", 5.0);
  p.set("slow", 20.0);
  ASSERT_EQ(p.names().size(), 2u);
  EXPECT_EQ(p.names()[0], "fast");
  EXPECT_EQ(p.names()[1], "slow");
  ASSERT_EQ(p.values().size(), 2u);
  EXPECT_DOUBLE_EQ(p.values()[0], 5.0);
  EXPECT_DOUBLE_EQ(p.values()[1], 20.0);
}

TEST(ParamSet, EqualitySameValues) {
  ParamSet a, b;
  a.set("x", 1.0);
  a.set("y", 2.0);
  b.set("x", 1.0);
  b.set("y", 2.0);
  EXPECT_TRUE(a == b);
  EXPECT_FALSE(a != b);
}

TEST(ParamSet, InequalityDifferentValue) {
  ParamSet a, b;
  a.set("x", 1.0);
  b.set("x", 2.0);
  EXPECT_TRUE(a != b);
}

TEST(ParamSet, InequalityDifferentNames) {
  ParamSet a, b;
  a.set("x", 1.0);
  b.set("y", 1.0);
  EXPECT_TRUE(a != b);
}

TEST(ParamSet, InequalityDifferentOrder) {
  ParamSet a, b;
  a.set("a", 1.0);
  a.set("b", 2.0);
  b.set("b", 2.0);
  b.set("a", 1.0);
  EXPECT_TRUE(a != b);
}

TEST(ParamSet, ToStringCanonical) {
  ParamSet p;
  p.set("fast", 5.0);
  p.set("slow", 20.0);
  p.set("stop", 1.5);
  EXPECT_EQ(p.to_string(), "fast=5 slow=20 stop=1.5");
}

TEST(ParamSet, ToStringEmptyForEmptySet) {
  ParamSet p;
  EXPECT_EQ(p.to_string(), "");
}

TEST(ParamSet, ToStringStableAcrossInstances) {
  ParamSet a, b;
  a.set("period", 10.0);
  b.set("period", 10.0);
  EXPECT_EQ(a.to_string(), b.to_string());
}

// ── ParameterSpace ──────────────────────────────────────────────────────────

TEST(ParameterSpace, EmptySpaceSingleTrivialCombo) {
  ParameterSpace s;
  EXPECT_TRUE(s.empty());
  // The product over an empty set of grids is one (trivial) combination.
  EXPECT_EQ(s.combo_count(), 1u);
  EXPECT_EQ(s.parameter_count(), 0u);
}

TEST(ParameterSpace, SingleGridComboCount) {
  ParameterSpace s;
  s.add_grid("a", {1.0, 2.0, 3.0});
  EXPECT_EQ(s.combo_count(), 3u);
  EXPECT_EQ(s.parameter_count(), 1u);
}

TEST(ParameterSpace, GridComboDecodeZeroIndex) {
  ParameterSpace s;
  s.add_grid("a", {10.0, 20.0});
  auto c = s.combo(0);
  EXPECT_DOUBLE_EQ(c.get("a"), 10.0);
}

TEST(ParameterSpace, GridComboDecodeLastIndex) {
  ParameterSpace s;
  s.add_grid("a", {10.0, 20.0});
  auto c = s.combo(1);
  EXPECT_DOUBLE_EQ(c.get("a"), 20.0);
}

TEST(ParameterSpace, ComboDecodeMixedRadixFirstVariesFastest) {
  ParameterSpace s;
  s.add_grid("a", {10.0, 20.0});
  s.add_grid("b", {1.0, 2.0, 3.0});
  s.add_grid("c", {5.0});
  EXPECT_EQ(s.combo_count(), 6u);
  {
    auto c = s.combo(0);
    EXPECT_DOUBLE_EQ(c.get("a"), 10.0);
    EXPECT_DOUBLE_EQ(c.get("b"), 1.0);
    EXPECT_DOUBLE_EQ(c.get("c"), 5.0);
  }
  {
    auto c = s.combo(3);
    EXPECT_DOUBLE_EQ(c.get("a"), 20.0);
    EXPECT_DOUBLE_EQ(c.get("b"), 2.0);
    EXPECT_DOUBLE_EQ(c.get("c"), 5.0);
  }
  {
    auto c = s.combo(4);
    EXPECT_DOUBLE_EQ(c.get("a"), 10.0);
    EXPECT_DOUBLE_EQ(c.get("b"), 3.0);
    EXPECT_DOUBLE_EQ(c.get("c"), 5.0);
  }
}

TEST(ParameterSpace, ComboOutOfRangeReturnsEmpty) {
  ParameterSpace s;
  s.add_grid("a", {1.0, 2.0});
  auto c = s.combo(2);
  EXPECT_EQ(c.size(), 0u);
}

TEST(ParameterSpace, AddRangeGeneratesArithmeticValues) {
  ParameterSpace s;
  s.add_range("r", 0.0, 2.0, 0.5);
  ASSERT_EQ(s.value_count(0), 5u);
  EXPECT_DOUBLE_EQ(s.values(0)[0], 0.0);
  EXPECT_DOUBLE_EQ(s.values(0)[4], 2.0);
}

TEST(ParameterSpace, AddRangeMinEqualsMax) {
  ParameterSpace s;
  s.add_range("r", 3.0, 3.0, 1.0);
  ASSERT_EQ(s.value_count(0), 1u);
  EXPECT_DOUBLE_EQ(s.values(0)[0], 3.0);
}

TEST(ParameterSpace, AddRangeInvalidStepEmpty) {
  ParameterSpace s;
  s.add_range("r", 0.0, 10.0, 0.0);
  EXPECT_EQ(s.value_count(0), 0u);
  EXPECT_EQ(s.combo_count(), 0u);
}

TEST(ParameterSpace, AddRangeReversedBoundsEmpty) {
  ParameterSpace s;
  s.add_range("r", 10.0, 0.0, 1.0);
  EXPECT_EQ(s.value_count(0), 0u);
}

TEST(ParameterSpace, IntRangeValues) {
  ParameterSpace s;
  s.add_int_range("p", 0, 10, 5);
  ASSERT_EQ(s.value_count(0), 3u);
  EXPECT_DOUBLE_EQ(s.values(0)[0], 0.0);
  EXPECT_DOUBLE_EQ(s.values(0)[1], 5.0);
  EXPECT_DOUBLE_EQ(s.values(0)[2], 10.0);
}

TEST(ParameterSpace, IntRangeDefaultStepIsOne) {
  ParameterSpace s;
  s.add_int_range("p", 0, 3);
  EXPECT_EQ(s.value_count(0), 4u);
}

TEST(ParameterSpace, IntRangeInvalidEmpty) {
  ParameterSpace s;
  s.add_int_range("p", 5, 1, 1);
  EXPECT_EQ(s.value_count(0), 0u);
}

TEST(ParameterSpace, LogScaleGeometricProgression) {
  ParameterSpace s;
  s.add_range("g", 1.0, 8.0, 2.0, /*log_scale=*/true);
  ASSERT_EQ(s.value_count(0), 4u);
  EXPECT_DOUBLE_EQ(s.values(0)[0], 1.0);
  EXPECT_DOUBLE_EQ(s.values(0)[1], 2.0);
  EXPECT_DOUBLE_EQ(s.values(0)[2], 4.0);
  EXPECT_DOUBLE_EQ(s.values(0)[3], 8.0);
}

TEST(ParameterSpace, LogScaleStepBelowOneEmpty) {
  ParameterSpace s;
  s.add_range("g", 1.0, 16.0, 0.5, /*log_scale=*/true);
  EXPECT_EQ(s.value_count(0), 0u);
}

TEST(ParameterSpace, ComboCountProduct) {
  ParameterSpace s;
  s.add_grid("a", {1.0, 2.0});
  s.add_grid("b", {1.0, 2.0, 3.0});
  s.add_grid("c", {1.0, 2.0, 3.0, 4.0});
  EXPECT_EQ(s.combo_count(), 2u * 3u * 4u);
}

TEST(ParameterSpace, ComboCountCappedOnOverflow) {
  ParameterSpace s;
  for (int i = 0; i < 40; ++i) {
    std::vector<double> v;
    for (int j = 0; j < 10; ++j) v.push_back(static_cast<double>(j));
    s.add_grid("p" + std::to_string(i), v);
  }
  EXPECT_EQ(s.combo_count(), std::numeric_limits<size_t>::max());
}

TEST(ParameterSpace, NamesInInsertionOrder) {
  ParameterSpace s;
  s.add_grid("z", {1.0});
  s.add_grid("a", {2.0});
  s.add_grid("m", {3.0});
  ASSERT_EQ(s.names().size(), 3u);
  EXPECT_EQ(s.names()[0], "z");
  EXPECT_EQ(s.names()[1], "a");
  EXPECT_EQ(s.names()[2], "m");
}

TEST(ParameterSpace, ContainsAndIndexOf) {
  ParameterSpace s;
  s.add_grid("fast", {1.0, 2.0});
  EXPECT_TRUE(s.contains("fast"));
  EXPECT_FALSE(s.contains("slow"));
  EXPECT_EQ(s.index_of("fast"), 0u);
  EXPECT_EQ(s.index_of("slow"), s.parameter_count());
}

TEST(ParameterSpace, ValueCountAndValuesAccessors) {
  ParameterSpace s;
  s.add_grid("a", {1.0, 2.0, 3.0});
  EXPECT_EQ(s.value_count(0), 3u);
  EXPECT_EQ(s.value_count(5), 0u);
  EXPECT_EQ(s.values(0).size(), 3u);
  EXPECT_EQ(s.values(7).size(), 0u);
}

TEST(ParameterSpace, ComboDeterministicSameInput) {
  ParameterSpace s;
  s.add_grid("a", {1.0, 2.0});
  s.add_grid("b", {10.0, 20.0, 30.0});
  EXPECT_EQ(s.combo(2), s.combo(2));
  EXPECT_EQ(s.combo(5).to_string(), "a=2 b=30");
}

TEST(ParameterSpace, Equality) {
  ParameterSpace a, b;
  a.add_grid("a", {1.0, 2.0});
  b.add_grid("a", {1.0, 2.0});
  EXPECT_TRUE(a == b);
  b.add_grid("b", {3.0});
  EXPECT_TRUE(a != b);
}

// ── OptimizationMetrics ─────────────────────────────────────────────────────

namespace {

StrategyStats make_stats(double net, double sharpe, double sortino, double calmar,
                         double dd, double pf, double win_rate, double exp,
                         double recovery, size_t trades) {
  StrategyStats s;
  s.net_profit = net;
  s.sharpe = sharpe;
  s.sortino = sortino;
  s.calmar = calmar;
  s.max_drawdown = dd;
  s.profit_factor = pf;
  s.win_rate = win_rate;
  s.expectancy = exp;
  s.recovery_factor = recovery;
  s.total_trades = trades;
  return s;
}

} // namespace

TEST(OptimizationMetrics, MapsAllStrategyStatsFields) {
  auto s = make_stats(1500.0, 1.2, 1.8, 0.9, 500.0, 1.7, 55.0, 12.5, 3.0, 42);
  s.total_return_pct = 1.5;
  s.annualized_return = 0.08;
  s.max_drawdown_pct = 0.5;
  std::vector<double> eq(50, 100000.0);
  auto m = compute_optimization_metrics(s, eq);
  EXPECT_DOUBLE_EQ(m.net_profit, 1500.0);
  EXPECT_DOUBLE_EQ(m.sharpe, 1.2);
  EXPECT_DOUBLE_EQ(m.sortino, 1.8);
  EXPECT_DOUBLE_EQ(m.calmar, 0.9);
  EXPECT_DOUBLE_EQ(m.max_drawdown, 500.0);
  EXPECT_DOUBLE_EQ(m.max_drawdown_pct, 0.5);
  EXPECT_DOUBLE_EQ(m.profit_factor, 1.7);
  EXPECT_DOUBLE_EQ(m.win_rate, 55.0);
  EXPECT_DOUBLE_EQ(m.expectancy, 12.5);
  EXPECT_DOUBLE_EQ(m.recovery_factor, 3.0);
  EXPECT_DOUBLE_EQ(m.total_return_pct, 1.5);
  EXPECT_DOUBLE_EQ(m.annualized_return, 0.08);
  EXPECT_EQ(m.trade_count, 42u);
}

TEST(OptimizationMetrics, StabilityPerfectLinearIs100) {
  auto s = make_stats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
  std::vector<double> eq = {0.0, 1.0, 2.0, 3.0, 4.0, 5.0};
  auto m = compute_optimization_metrics(s, eq);
  EXPECT_DOUBLE_EQ(m.stability, 100.0);
}

TEST(OptimizationMetrics, StabilityFlatEquityIs100) {
  auto s = make_stats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
  std::vector<double> eq(6, 100.0);
  auto m = compute_optimization_metrics(s, eq);
  EXPECT_DOUBLE_EQ(m.stability, 100.0);
}

TEST(OptimizationMetrics, StabilityOscillatingIsLow) {
  auto s = make_stats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
  std::vector<double> eq = {100.0, 0.0, 100.0, 0.0, 100.0, 0.0};
  auto m = compute_optimization_metrics(s, eq);
  EXPECT_GE(m.stability, 0.0);
  EXPECT_LT(m.stability, 20.0);
}

TEST(OptimizationMetrics, StabilityTwoPointsIs100) {
  auto s = make_stats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
  std::vector<double> eq = {100.0, 200.0};
  auto m = compute_optimization_metrics(s, eq);
  EXPECT_DOUBLE_EQ(m.stability, 100.0);
}

TEST(OptimizationMetrics, StabilitySinglePointZero) {
  auto s = make_stats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
  std::vector<double> eq = {100.0};
  auto m = compute_optimization_metrics(s, eq);
  EXPECT_DOUBLE_EQ(m.stability, 0.0);
}

TEST(OptimizationMetrics, StabilityEmptyZero) {
  auto s = make_stats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
  auto m = compute_optimization_metrics(s, {});
  EXPECT_DOUBLE_EQ(m.stability, 0.0);
}

TEST(OptimizationMetrics, StabilityMonotonicTrendingIsHigh) {
  auto s = make_stats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
  std::vector<double> eq = {100.0, 101.0, 102.0, 102.9, 104.0, 105.0};
  auto m = compute_optimization_metrics(s, eq);
  EXPECT_GT(m.stability, 90.0);
}

TEST(OptimizationMetrics, StabilityAlwaysWithinBounds) {
  auto s = make_stats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
  std::vector<double> eq = {100.0, 500.0, 100.0, 500.0, 100.0, 500.0};
  auto m = compute_optimization_metrics(s, eq);
  EXPECT_GE(m.stability, 0.0);
  EXPECT_LE(m.stability, 100.0);
}

TEST(OptimizationMetrics, RankDirection) {
  EXPECT_EQ(rank_direction(OptimizationMetric::MaxDrawdown), -1);
  EXPECT_EQ(rank_direction(OptimizationMetric::NetProfit), 1);
  EXPECT_EQ(rank_direction(OptimizationMetric::Sharpe), 1);
  EXPECT_EQ(rank_direction(OptimizationMetric::Sortino), 1);
  EXPECT_EQ(rank_direction(OptimizationMetric::Calmar), 1);
  EXPECT_EQ(rank_direction(OptimizationMetric::ProfitFactor), 1);
  EXPECT_EQ(rank_direction(OptimizationMetric::WinRate), 1);
  EXPECT_EQ(rank_direction(OptimizationMetric::Expectancy), 1);
  EXPECT_EQ(rank_direction(OptimizationMetric::RecoveryFactor), 1);
  EXPECT_EQ(rank_direction(OptimizationMetric::TradeCount), 1);
  EXPECT_EQ(rank_direction(OptimizationMetric::Stability), 1);
}

// ── Optimizer: validation ───────────────────────────────────────────────────

TEST(Optimizer, EmptyBarsError) {
  ParameterSpace space;
  space.add_grid("a", {1.0});
  Optimizer opt(zero_cost());
  auto res = opt.optimize({}, space, interval_gen());
  ASSERT_TRUE(res.is_err());
  EXPECT_EQ(res.error().code(), ErrorCode::InsufficientData);
}

TEST(Optimizer, InvalidBarError) {
  ParameterSpace space;
  space.add_grid("a", {1.0});
  std::vector<OHLCV> bars = {mk(100, 99, 101, 100, 0)}; // high < low
  Optimizer opt(zero_cost());
  auto res = opt.optimize(bars, space, interval_gen());
  ASSERT_TRUE(res.is_err());
  EXPECT_EQ(res.error().code(), ErrorCode::InvalidArgument);
}

TEST(Optimizer, NonMonotonicTimestampsError) {
  ParameterSpace space;
  space.add_grid("a", {1.0});
  std::vector<OHLCV> bars = {mk(100, 101, 99, 100, 5), mk(100, 101, 99, 100, 3)};
  Optimizer opt(zero_cost());
  auto res = opt.optimize(bars, space, interval_gen());
  ASSERT_TRUE(res.is_err());
  EXPECT_EQ(res.error().code(), ErrorCode::InvalidArgument);
}

TEST(Optimizer, EmptySpaceError) {
  auto bars = make_bars(50);
  Optimizer opt(zero_cost());
  auto res = opt.optimize(bars, ParameterSpace(), interval_gen());
  ASSERT_TRUE(res.is_err());
  EXPECT_EQ(res.error().code(), ErrorCode::InvalidArgument);
}

TEST(Optimizer, ZeroComboSpaceError) {
  auto bars = make_bars(50);
  ParameterSpace space;
  space.add_range("r", 5.0, 1.0, 1.0); // empty grid
  Optimizer opt(zero_cost());
  auto res = opt.optimize(bars, space, interval_gen());
  ASSERT_TRUE(res.is_err());
  EXPECT_EQ(res.error().code(), ErrorCode::InvalidArgument);
}

TEST(Optimizer, OverflowSpaceError) {
  auto bars = make_bars(50);
  ParameterSpace space;
  for (int i = 0; i < 40; ++i) {
    std::vector<double> v;
    for (int j = 0; j < 10; ++j) v.push_back(static_cast<double>(j));
    space.add_grid("p" + std::to_string(i), v);
  }
  Optimizer opt(zero_cost());
  auto res = opt.optimize(bars, space, interval_gen());
  ASSERT_TRUE(res.is_err());
  EXPECT_EQ(res.error().code(), ErrorCode::NumericOverflow);
}

TEST(Optimizer, ZeroSamplesReturnsEmptyResult) {
  auto bars = make_bars(50);
  ParameterSpace space;
  space.add_grid("a", {1.0, 2.0, 3.0});
  Optimizer opt(zero_cost(), seeded_cfg(1, 0));
  auto res = opt.optimize(bars, space, interval_gen());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  EXPECT_EQ(r.requested, 0u);
  EXPECT_EQ(r.evaluated, 0u);
  EXPECT_TRUE(r.empty());
  EXPECT_EQ(r.best(), nullptr);
}

// ── Optimizer: grid search ──────────────────────────────────────────────────

TEST(Optimizer, GridSweepEvaluatesAllCombos) {
  auto bars = make_bars(200);
  ParameterSpace space;
  space.add_int_range("period", 5, 15, 5); // 3 values
  Optimizer opt(zero_cost(), grid_cfg());
  auto res = opt.optimize(bars, space, interval_gen());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  EXPECT_EQ(r.requested, 3u);
  EXPECT_EQ(r.evaluated, 3u);
  EXPECT_EQ(r.failed, 0u);
  EXPECT_EQ(r.ranked.size(), 3u);
}

TEST(Optimizer, GridSweepCombosMatchSpaceDecode) {
  auto bars = make_bars(200);
  ParameterSpace space;
  space.add_grid("a", {10.0, 20.0});
  space.add_grid("b", {1.0, 2.0, 3.0});
  const size_t total = space.combo_count();
  Optimizer opt(zero_cost(), grid_cfg());
  auto res = opt.optimize(bars, space, interval_gen());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  ASSERT_EQ(r.ranked.size(), total);
  for (size_t i = 0; i < total; ++i) {
    EXPECT_EQ(r.ranked[i].evaluation.params, space.combo(i));
  }
}

TEST(Optimizer, GridDefaultRanksNetProfitDescending) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  Optimizer opt(zero_cost(), grid_cfg(OptimizationMetric::NetProfit));
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  ASSERT_FALSE(r.empty());
  for (size_t i = 1; i < r.ranked.size(); ++i) {
    EXPECT_GE(r.ranked[i - 1].evaluation.metrics.net_profit,
              r.ranked[i].evaluation.metrics.net_profit);
  }
}

TEST(Optimizer, RankingTieBreakByComboIndex) {
  auto bars = make_bars(200);
  ParameterSpace space;
  space.add_grid("period", {5.0});
  space.add_grid("dummy", {1.0, 2.0}); // generator ignores `dummy`
  Optimizer opt(zero_cost(), grid_cfg());
  auto res = opt.optimize(bars, space, interval_gen());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  ASSERT_EQ(r.ranked.size(), 2u);
  EXPECT_EQ(r.ranked[0].evaluation.combo_index, 0u);
  EXPECT_EQ(r.ranked[1].evaluation.combo_index, 1u);
  EXPECT_DOUBLE_EQ(r.ranked[0].evaluation.metrics.net_profit,
                   r.ranked[1].evaluation.metrics.net_profit);
}

TEST(Optimizer, RankValueMatchesMetric) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  Optimizer opt(zero_cost(), grid_cfg(OptimizationMetric::Sharpe));
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  ASSERT_FALSE(r.empty());
  for (const auto& rs : r.ranked) {
    EXPECT_DOUBLE_EQ(rs.rank_value, rs.evaluation.metrics.sharpe);
  }
  for (size_t i = 1; i < r.ranked.size(); ++i) {
    EXPECT_GE(r.ranked[i - 1].evaluation.metrics.sharpe,
              r.ranked[i].evaluation.metrics.sharpe);
  }
}

TEST(Optimizer, MaxDrawdownRankedAscending) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  space.add_grid("stop", {0.5, 1.0, 2.0});
  Optimizer opt(zero_cost(),
                grid_cfg(OptimizationMetric::MaxDrawdown));
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  ASSERT_FALSE(r.empty());
  for (size_t i = 1; i < r.ranked.size(); ++i) {
    EXPECT_LE(r.ranked[i - 1].evaluation.metrics.max_drawdown,
              r.ranked[i].evaluation.metrics.max_drawdown);
  }
}

TEST(Optimizer, RankByProfitFactor) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  Optimizer opt(zero_cost(), grid_cfg(OptimizationMetric::ProfitFactor));
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  for (size_t i = 1; i < r.ranked.size(); ++i) {
    EXPECT_GE(r.ranked[i - 1].evaluation.metrics.profit_factor,
              r.ranked[i].evaluation.metrics.profit_factor);
  }
}

TEST(Optimizer, RankByWinRate) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  Optimizer opt(zero_cost(), grid_cfg(OptimizationMetric::WinRate));
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  for (size_t i = 1; i < r.ranked.size(); ++i) {
    EXPECT_GE(r.ranked[i - 1].evaluation.metrics.win_rate,
              r.ranked[i].evaluation.metrics.win_rate);
  }
}

TEST(Optimizer, RankByTradeCount) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  Optimizer opt(zero_cost(), grid_cfg(OptimizationMetric::TradeCount));
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  for (size_t i = 1; i < r.ranked.size(); ++i) {
    EXPECT_GE(r.ranked[i - 1].evaluation.metrics.trade_count,
              r.ranked[i].evaluation.metrics.trade_count);
  }
}

TEST(Optimizer, RankByStability) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  Optimizer opt(zero_cost(), grid_cfg(OptimizationMetric::Stability));
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  for (size_t i = 1; i < r.ranked.size(); ++i) {
    EXPECT_GE(r.ranked[i - 1].evaluation.metrics.stability,
              r.ranked[i].evaluation.metrics.stability);
  }
}

TEST(Optimizer, RankByRecoveryFactor) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  Optimizer opt(zero_cost(), grid_cfg(OptimizationMetric::RecoveryFactor));
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  for (size_t i = 1; i < r.ranked.size(); ++i) {
    EXPECT_GE(r.ranked[i - 1].evaluation.metrics.recovery_factor,
              r.ranked[i].evaluation.metrics.recovery_factor);
  }
}

TEST(Optimizer, RankByExpectancy) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  Optimizer opt(zero_cost(), grid_cfg(OptimizationMetric::Expectancy));
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  for (size_t i = 1; i < r.ranked.size(); ++i) {
    EXPECT_GE(r.ranked[i - 1].evaluation.metrics.expectancy,
              r.ranked[i].evaluation.metrics.expectancy);
  }
}

TEST(Optimizer, RankBySortino) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  Optimizer opt(zero_cost(), grid_cfg(OptimizationMetric::Sortino));
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  for (size_t i = 1; i < r.ranked.size(); ++i) {
    EXPECT_GE(r.ranked[i - 1].evaluation.metrics.sortino,
              r.ranked[i].evaluation.metrics.sortino);
  }
}

TEST(Optimizer, RankByCalmar) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  Optimizer opt(zero_cost(), grid_cfg(OptimizationMetric::Calmar));
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  for (size_t i = 1; i < r.ranked.size(); ++i) {
    EXPECT_GE(r.ranked[i - 1].evaluation.metrics.calmar,
              r.ranked[i].evaluation.metrics.calmar);
  }
}

TEST(Optimizer, TopNRestrictsRankedSize) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  Optimizer opt(zero_cost(), grid_cfg(OptimizationMetric::NetProfit, /*top_n=*/2));
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  EXPECT_EQ(r.evaluated, 9u);
  EXPECT_EQ(r.ranked.size(), 2u);
  EXPECT_EQ(r.ranked[0].rank, 1u);
  EXPECT_EQ(r.ranked[1].rank, 2u);
}

TEST(Optimizer, TopNKeepsBestFirst) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  Optimizer opt(zero_cost(), grid_cfg(OptimizationMetric::NetProfit));
  auto all = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(all.is_ok());
  Optimizer opt5(zero_cost(), grid_cfg(OptimizationMetric::NetProfit, /*top_n=*/3));
  auto top3 = opt5.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(top3.is_ok());
  ASSERT_FALSE(all.value().ranked.empty());
  ASSERT_EQ(top3.value().ranked.size(), 3u);
  for (size_t i = 0; i < 3; ++i) {
    EXPECT_EQ(top3.value().ranked[i].evaluation.combo_index,
              all.value().ranked[i].evaluation.combo_index);
  }
}

TEST(Optimizer, BestReturnsTopStrategy) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  Optimizer opt(zero_cost(), grid_cfg());
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  ASSERT_FALSE(r.empty());
  ASSERT_NE(r.best(), nullptr);
  EXPECT_EQ(r.best(), &r.ranked.front());
  EXPECT_DOUBLE_EQ(r.best()->evaluation.metrics.net_profit,
                   r.ranked[0].evaluation.metrics.net_profit);
}

// ── Optimizer: random / seeded search ───────────────────────────────────────

TEST(Optimizer, SeededSearchDeterministicSameSeed) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  space.add_grid("stop", {0.5, 1.0, 2.0});
  Optimizer a(zero_cost(), seeded_cfg(1234, 20));
  Optimizer b(zero_cost(), seeded_cfg(1234, 20));
  auto ra = a.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  auto rb = b.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(ra.is_ok());
  ASSERT_TRUE(rb.is_ok());
  EXPECT_EQ(ra.value().compute_result_hash(), rb.value().compute_result_hash());
  ASSERT_EQ(ra.value().ranked.size(), rb.value().ranked.size());
  for (size_t i = 0; i < ra.value().ranked.size(); ++i) {
    EXPECT_EQ(ra.value().ranked[i].evaluation.combo_index,
              rb.value().ranked[i].evaluation.combo_index);
  }
}

TEST(Optimizer, SeededSearchSamplesRequestedCount) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  space.add_grid("stop", {0.5, 1.0, 2.0});
  Optimizer opt(zero_cost(), seeded_cfg(7, 10));
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  EXPECT_EQ(r.requested, 10u);
  EXPECT_EQ(r.evaluated, 10u);
  EXPECT_EQ(r.ranked.size(), 10u);
  EXPECT_EQ(r.seed, 7u);
  EXPECT_EQ(r.search_type, SearchType::Seeded);
}

TEST(Optimizer, SeededSearchSamplesCappedAtGridSize) {
  auto bars = make_bars(200);
  ParameterSpace space;
  space.add_int_range("period", 5, 15, 5); // 3 combos
  Optimizer opt(zero_cost(), seeded_cfg(9, 100));
  auto res = opt.optimize(bars, space, interval_gen());
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  EXPECT_EQ(r.requested, 3u);
  EXPECT_EQ(r.evaluated, 3u);
}

TEST(Optimizer, DifferentSeedsSampleDifferentCombos) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_int_range("a", 2, 6, 1);   // 5
  space.add_int_range("b", 3, 7, 1);   // 5
  space.add_int_range("c", 1, 4, 1);   // 4
  space.add_int_range("d", 1, 4, 1);   // 4  -> 400 combos
  Optimizer o1(zero_cost(), seeded_cfg(1, 20));
  Optimizer o2(zero_cost(), seeded_cfg(2, 20));
  auto r1 = o1.optimize(bars, space, interval_gen());
  auto r2 = o2.optimize(bars, space, interval_gen());
  ASSERT_TRUE(r1.is_ok());
  ASSERT_TRUE(r2.is_ok());
  std::unordered_set<size_t> s1, s2;
  for (const auto& rs : r1.value().ranked) s1.insert(rs.evaluation.combo_index);
  for (const auto& rs : r2.value().ranked) s2.insert(rs.evaluation.combo_index);
  EXPECT_EQ(s1.size(), 20u);
  EXPECT_EQ(s2.size(), 20u);
  EXPECT_NE(s1, s2);
}

TEST(Optimizer, RandomSearchRecordsSeedAndIsReproducibleViaSeeded) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  space.add_grid("stop", {0.5, 1.0, 2.0});
  OptimizerConfig rnd_cfg;
  rnd_cfg.search_type = SearchType::Random;
  rnd_cfg.random_samples = 15;
  rnd_cfg.max_parallelism = 1;
  Optimizer rnd(zero_cost(), rnd_cfg);
  auto r = rnd.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(r.is_ok());
  const auto& res = r.value();
  EXPECT_EQ(res.search_type, SearchType::Random);
  EXPECT_EQ(res.requested, 15u);
  EXPECT_EQ(res.evaluated, 15u);
  EXPECT_NE(res.seed, 0u);

  // Replaying the recorded seed through a Seeded search reproduces the result.
  Optimizer replay(zero_cost(), seeded_cfg(res.seed, 15));
  auto rr = replay.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(rr.is_ok());
  EXPECT_EQ(res.compute_result_hash(), rr.value().compute_result_hash());
}

TEST(Optimizer, RandomSearchSamplesRequestedCount) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  space.add_grid("stop", {0.5, 1.0, 2.0});
  OptimizerConfig cfg;
  cfg.search_type = SearchType::Random;
  cfg.random_samples = 8;
  Optimizer opt(zero_cost(), cfg);
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  EXPECT_EQ(res.value().requested, 8u);
}

// ── Optimizer: parallel execution ───────────────────────────────────────────

TEST(Optimizer, ParallelDeterministicMatchesSingleThread) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  space.add_grid("stop", {0.5, 1.0, 2.0});
  Optimizer single(zero_cost(), grid_cfg(OptimizationMetric::NetProfit, 0, 1));
  Optimizer parallel(zero_cost(), grid_cfg(OptimizationMetric::NetProfit, 0, 8));
  auto rs = single.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  auto rp = parallel.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(rs.is_ok());
  ASSERT_TRUE(rp.is_ok());
  EXPECT_EQ(rs.value().compute_result_hash(), rp.value().compute_result_hash());
  ASSERT_EQ(rs.value().ranked.size(), rp.value().ranked.size());
  for (size_t i = 0; i < rs.value().ranked.size(); ++i) {
    EXPECT_EQ(rs.value().ranked[i].evaluation.combo_index,
              rp.value().ranked[i].evaluation.combo_index);
    EXPECT_DOUBLE_EQ(rs.value().ranked[i].rank_value,
                     rp.value().ranked[i].rank_value);
  }
}

TEST(Optimizer, SeededParallelMatchesSeededSingleThread) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  space.add_grid("stop", {0.5, 1.0, 2.0});
  Optimizer single(zero_cost(), seeded_cfg(99, 25, OptimizationMetric::NetProfit, 1));
  Optimizer parallel(zero_cost(), seeded_cfg(99, 25, OptimizationMetric::NetProfit, 8));
  auto rs = single.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  auto rp = parallel.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(rs.is_ok());
  ASSERT_TRUE(rp.is_ok());
  EXPECT_EQ(rs.value().compute_result_hash(), rp.value().compute_result_hash());
}

TEST(Optimizer, ConcurrentOptimizeCallsOnSharedInstance) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  space.add_grid("stop", {0.5, 1.0, 2.0});
  Optimizer shared(zero_cost(), seeded_cfg(42, 30, OptimizationMetric::NetProfit, 4));
  OptimizationResult r1, r2;
  std::atomic<bool> ok1{false}, ok2{false};
  std::thread t1([&] {
    auto res = shared.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
    if (res.is_ok()) {
      r1 = std::move(res).value();
      ok1 = true;
    }
  });
  std::thread t2([&] {
    auto res = shared.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
    if (res.is_ok()) {
      r2 = std::move(res).value();
      ok2 = true;
    }
  });
  t1.join();
  t2.join();
  ASSERT_TRUE(ok1.load());
  ASSERT_TRUE(ok2.load());
  EXPECT_EQ(r1.compute_result_hash(), r2.compute_result_hash());
}

// ── Optimizer: config providers & errors ────────────────────────────────────

TEST(Optimizer, ConfigProviderAffectsResults) {
  auto bars = make_bars(300);
  ParamSet params;
  params.set("fast", 5.0);
  params.set("slow", 20.0);
  auto gen = sma_cross_gen();

  auto tight = FunctionConfigProvider([](const ParamSet&) {
    strategy::StrategyConfig cfg = zero_cost();
    cfg.trade.stop_loss = 0.5;
    cfg.trade.take_profit = 0.8;
    return cfg;
  });
  auto loose = FunctionConfigProvider([](const ParamSet&) {
    strategy::StrategyConfig cfg = zero_cost();
    cfg.trade.stop_loss = 50.0;
    cfg.trade.take_profit = 100.0;
    return cfg;
  });

  Optimizer opt(zero_cost());
  auto a = opt.evaluate_combo(bars, params, gen, &tight);
  auto b = opt.evaluate_combo(bars, params, gen, &loose);
  ASSERT_TRUE(a.is_ok());
  ASSERT_TRUE(b.is_ok());
  EXPECT_NE(a.value().metrics.net_profit, b.value().metrics.net_profit);
}

TEST(Optimizer, NullConfigProviderUsesBaseConfig) {
  auto bars = make_bars(200);
  ParameterSpace space;
  space.add_grid("period", {5.0});
  strategy::StrategyConfig base = zero_cost();
  base.trade.stop_loss = 2.0;
  base.trade.take_profit = 5.0;
  Optimizer opt(base, grid_cfg());
  auto res = opt.optimize(bars, space, interval_gen());
  ASSERT_TRUE(res.is_ok());
  ASSERT_EQ(res.value().ranked.size(), 1u);
  EXPECT_GT(res.value().ranked[0].evaluation.metrics.trade_count, 0u);
}

TEST(Optimizer, SignalGeneratorReceivesParams) {
  auto bars = make_bars(200);
  ParameterSpace space;
  space.add_grid("period", {5.0, 10.0, 20.0});
  std::vector<std::string> received;
  auto capturing = FunctionSignalGenerator([&](const std::vector<OHLCV>& b,
                                               const ParamSet& p) {
    received.push_back(p.to_string());
    return interval_gen().generate(b, p);
  });
  OptimizerConfig cfg = grid_cfg();
  cfg.top_n = 1;  // keep the sweep single-pass per combo; re-evaluate top-1
  Optimizer opt(zero_cost(), cfg);
  auto res = opt.optimize(bars, space, capturing);
  ASSERT_TRUE(res.is_ok());
  // One call per combo during the sweep, plus one for the retained top strategy.
  EXPECT_EQ(received.size(), 4u);
  for (const char* want : {"period=5", "period=10", "period=20"}) {
    EXPECT_TRUE(std::find(received.begin(), received.end(), want) !=
                received.end());
  }
}

TEST(Optimizer, EvaluateComboSingle) {
  auto bars = make_bars(200);
  ParamSet params;
  params.set("period", 5);
  Optimizer opt(zero_cost());
  auto res = opt.evaluate_combo(bars, params, interval_gen());
  ASSERT_TRUE(res.is_ok());
  const auto& ev = res.value();
  EXPECT_EQ(ev.params, params);
  EXPECT_EQ(ev.simulation.equity_curve.size(), bars.size());
  EXPECT_GT(ev.metrics.trade_count, 0u);
}

TEST(Optimizer, EvaluateComboBadSignalsError) {
  auto bars = make_bars(100);
  ParamSet params;
  auto bad = FunctionSignalGenerator([](const std::vector<OHLCV>& b,
                                        const ParamSet&) {
    StrategySignal sig;
    sig.bar_index = static_cast<int64_t>(b.size()); // out of range
    sig.action = SignalAction::Open;
    return std::vector<StrategySignal>{sig};
  });
  Optimizer opt(zero_cost());
  auto res = opt.evaluate_combo(bars, params, bad);
  ASSERT_TRUE(res.is_err());
  EXPECT_EQ(res.error().code(), ErrorCode::OutOfBounds);
}

TEST(Optimizer, OptimizeSkipsErroredCombosAndCountsFailed) {
  auto bars = make_bars(100);
  ParameterSpace space;
  space.add_grid("bad", {0.0, 1.0});
  auto flaky = FunctionSignalGenerator([](const std::vector<OHLCV>& b,
                                          const ParamSet& p) {
    if (p.get_int("bad") == 1) {
      StrategySignal sig;
      sig.bar_index = static_cast<int64_t>(b.size()); // invalid
      sig.action = SignalAction::Open;
      return std::vector<StrategySignal>{sig};
    }
    return interval_gen().generate(b, p);
  });
  Optimizer opt(zero_cost(), grid_cfg());
  auto res = opt.optimize(bars, space, flaky);
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  EXPECT_EQ(r.requested, 2u);
  EXPECT_EQ(r.evaluated, 1u);
  EXPECT_EQ(r.failed, 1u);
  EXPECT_EQ(r.ranked.size(), 1u);
  EXPECT_EQ(r.ranked[0].evaluation.combo_index, 0u);
}

TEST(Optimizer, AllCombosFailProducesEmptyRanking) {
  auto bars = make_bars(100);
  ParameterSpace space;
  space.add_grid("bad", {0.0, 1.0});
  auto always_bad = FunctionSignalGenerator([](const std::vector<OHLCV>& b,
                                               const ParamSet&) {
    StrategySignal sig;
    sig.bar_index = static_cast<int64_t>(b.size());
    sig.action = SignalAction::Open;
    return std::vector<StrategySignal>{sig};
  });
  Optimizer opt(zero_cost(), grid_cfg());
  auto res = opt.optimize(bars, space, always_bad);
  ASSERT_TRUE(res.is_ok());
  const auto& r = res.value();
  EXPECT_EQ(r.evaluated, 0u);
  EXPECT_EQ(r.failed, 2u);
  EXPECT_TRUE(r.empty());
  EXPECT_EQ(r.best(), nullptr);
}

TEST(Optimizer, ParameterNamesRecordedInResult) {
  auto bars = make_bars(200);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0});
  space.add_grid("slow", {10.0, 20.0});
  Optimizer opt(zero_cost(), grid_cfg());
  auto res = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const auto& names = res.value().parameter_names;
  ASSERT_EQ(names.size(), 2u);
  EXPECT_EQ(names[0], "fast");
  EXPECT_EQ(names[1], "slow");
}

// ── Optimizer: result hashing ───────────────────────────────────────────────

TEST(Optimizer, ResultHashDeterministicSameInput) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0});
  space.add_grid("slow", {10.0, 20.0});
  Optimizer opt(zero_cost(), grid_cfg());
  auto a = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  auto b = opt.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(a.is_ok());
  ASSERT_TRUE(b.is_ok());
  EXPECT_EQ(a.value().compute_result_hash(), b.value().compute_result_hash());
}

TEST(Optimizer, ResultHashDiffersForDifferentSpaces) {
  auto bars = make_bars(300);
  ParameterSpace space1, space2;
  space1.add_grid("fast", {3.0, 5.0});
  space1.add_grid("slow", {10.0, 20.0});
  space2.add_grid("fast", {3.0, 5.0, 9.0});
  space2.add_grid("slow", {10.0, 20.0});
  Optimizer opt(zero_cost(), grid_cfg());
  auto a = opt.optimize(bars, space1, sma_cross_gen(), &stop_tp_provider());
  auto b = opt.optimize(bars, space2, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(a.is_ok());
  ASSERT_TRUE(b.is_ok());
  EXPECT_NE(a.value().compute_result_hash(), b.value().compute_result_hash());
}

TEST(Optimizer, ResultHashDiffersForDifferentSeeds) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0});
  space.add_grid("slow", {10.0, 20.0});
  Optimizer a(zero_cost(), seeded_cfg(1, 3));
  Optimizer b(zero_cost(), seeded_cfg(2, 3));
  auto ra = a.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  auto rb = b.optimize(bars, space, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(ra.is_ok());
  ASSERT_TRUE(rb.is_ok());
  EXPECT_NE(ra.value().compute_result_hash(), rb.value().compute_result_hash());
}

TEST(Optimizer, ResultHashIsNonEmptyHex) {
  auto bars = make_bars(200);
  ParameterSpace space;
  space.add_grid("period", {5.0});
  Optimizer opt(zero_cost(), grid_cfg());
  auto res = opt.optimize(bars, space, interval_gen());
  ASSERT_TRUE(res.is_ok());
  const std::string h = res.value().compute_result_hash();
  EXPECT_EQ(h.size(), 16u);
  for (char c : h) EXPECT_TRUE((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'));
}

// ── ResearchRunner ──────────────────────────────────────────────────────────

TEST(ResearchRunner, RunGridDefault) {
  auto bars = make_bars(200);
  ParameterSpace space;
  space.add_int_range("period", 5, 15, 5);
  ResearchRunner runner(zero_cost());
  ResearchPlan plan;
  plan.space = space;
  auto res = runner.run(plan, bars, interval_gen());
  ASSERT_TRUE(res.is_ok());
  EXPECT_EQ(res.value().search_type, SearchType::Grid);
  EXPECT_EQ(res.value().evaluated, 3u);
}

TEST(ResearchRunner, RunSeededDeterministic) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  ResearchRunner runner(zero_cost());
  ResearchPlan plan;
  plan.space = space;
  plan.search_type = SearchType::Seeded;
  plan.seed = 555;
  plan.random_samples = 12;
  auto a = runner.run(plan, bars, sma_cross_gen(), &stop_tp_provider());
  auto b = runner.run(plan, bars, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(a.is_ok());
  ASSERT_TRUE(b.is_ok());
  EXPECT_EQ(a.value().compute_result_hash(), b.value().compute_result_hash());
  EXPECT_EQ(a.value().seed, 555u);
}

TEST(ResearchRunner, RunRandomCount) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  ResearchRunner runner(zero_cost());
  ResearchPlan plan;
  plan.space = space;
  plan.search_type = SearchType::Random;
  plan.random_samples = 6;
  auto res = runner.run(plan, bars, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  EXPECT_EQ(res.value().requested, 6u);
}

TEST(ResearchRunner, EvaluateComboProducesSimulation) {
  auto bars = make_bars(200);
  ParamSet params;
  params.set("period", 5);
  ResearchRunner runner(zero_cost());
  auto res = runner.evaluate_combo(bars, params, interval_gen());
  ASSERT_TRUE(res.is_ok());
  const auto& ev = res.value();
  EXPECT_EQ(ev.simulation.equity_curve.size(), bars.size());
  EXPECT_EQ(ev.simulation.drawdown_curve.size(), bars.size());
  EXPECT_FALSE(ev.simulation.input_hash.empty());
  EXPECT_FALSE(ev.simulation.result_hash.empty());
  EXPECT_EQ(ev.simulation.final_equity, ev.final_equity);
}

TEST(ResearchRunner, EvaluateComboEquityCurveLength) {
  auto bars = make_bars(150);
  ParamSet params;
  params.set("period", 3);
  ResearchRunner runner(zero_cost());
  auto res = runner.evaluate_combo(bars, params, interval_gen());
  ASSERT_TRUE(res.is_ok());
  EXPECT_EQ(res.value().simulation.equity_curve.size(), 150u);
}

TEST(ResearchRunner, BaseConfigUsedWhenNoProvider) {
  auto bars = make_bars(200);
  strategy::StrategyConfig base = zero_cost();
  base.trade.stop_loss = 3.0;
  base.trade.take_profit = 6.0;
  ResearchRunner runner(base);
  ParamSet params;
  params.set("period", 5);
  auto res = runner.evaluate_combo(bars, params, interval_gen());
  ASSERT_TRUE(res.is_ok());
  EXPECT_GT(res.value().metrics.trade_count, 0u);
  EXPECT_GT(res.value().final_equity, 0.0);
}

TEST(ResearchRunner, RunGridTopN) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  ResearchRunner runner(zero_cost());
  ResearchPlan plan;
  plan.space = space;
  plan.top_n = 2;
  auto res = runner.run(plan, bars, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  EXPECT_EQ(res.value().ranked.size(), 2u);
}

TEST(ResearchRunner, PlanRankMetricRespected) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  ResearchRunner runner(zero_cost());
  ResearchPlan plan;
  plan.space = space;
  plan.rank_metric = OptimizationMetric::Sortino;
  auto res = runner.run(plan, bars, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  EXPECT_EQ(res.value().rank_metric, OptimizationMetric::Sortino);
  for (size_t i = 1; i < res.value().ranked.size(); ++i) {
    EXPECT_GE(res.value().ranked[i - 1].evaluation.metrics.sortino,
              res.value().ranked[i].evaluation.metrics.sortino);
  }
}

TEST(ResearchRunner, PlanParallelism) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  ResearchRunner runner(zero_cost());
  ResearchPlan plan;
  plan.space = space;
  plan.max_parallelism = 4;
  auto res = runner.run(plan, bars, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  EXPECT_EQ(res.value().evaluated, 9u);
}

TEST(ResearchRunner, ConvenienceRunGrid) {
  auto bars = make_bars(200);
  ParameterSpace space;
  space.add_int_range("period", 5, 15, 5);
  ResearchRunner runner(zero_cost());
  auto res = runner.run_grid(space, bars, interval_gen());
  ASSERT_TRUE(res.is_ok());
  EXPECT_EQ(res.value().search_type, SearchType::Grid);
  EXPECT_EQ(res.value().evaluated, 3u);
}

TEST(ResearchRunner, ConvenienceRunSeeded) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  ResearchRunner runner(zero_cost());
  auto res = runner.run_seeded(space, bars, 8, 4242, sma_cross_gen(),
                               &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  EXPECT_EQ(res.value().requested, 8u);
  EXPECT_EQ(res.value().seed, 4242u);
}

TEST(ResearchRunner, ConvenienceRunRandom) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  ResearchRunner runner(zero_cost());
  auto res = runner.run_random(space, bars, 5, sma_cross_gen(),
                               &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  EXPECT_EQ(res.value().requested, 5u);
  EXPECT_EQ(res.value().search_type, SearchType::Random);
}

TEST(ResearchRunner, SummaryContainsTopStrategyAndMetrics) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0});
  space.add_grid("slow", {10.0, 20.0});
  ResearchRunner runner(zero_cost());
  auto res = runner.run_grid(space, bars, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const std::string s = optimization_summary(res.value());
  EXPECT_NE(s.find("optimization summary"), std::string::npos);
  EXPECT_NE(s.find("rank=1"), std::string::npos);
  EXPECT_NE(s.find("net_profit="), std::string::npos);
  EXPECT_NE(s.find("sharpe="), std::string::npos);
  EXPECT_NE(s.find("max_dd="), std::string::npos);
  EXPECT_NE(s.find("fast="), std::string::npos);
}

TEST(ResearchRunner, SummaryTopLimitRespected) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  ResearchRunner runner(zero_cost());
  auto res = runner.run_grid(space, bars, sma_cross_gen(), &stop_tp_provider());
  ASSERT_TRUE(res.is_ok());
  const std::string s = optimization_summary(res.value(), 2);
  EXPECT_NE(s.find("rank=2"), std::string::npos);
  EXPECT_EQ(s.find("rank=3"), std::string::npos);
}

TEST(ResearchRunner, SetBaseConfig) {
  ResearchRunner runner(zero_cost());
  strategy::StrategyConfig base = zero_cost();
  base.trade.stop_loss = 1.0;
  runner.set_base_config(base);
  EXPECT_DOUBLE_EQ(runner.base_config().trade.stop_loss, 1.0);
}

TEST(ResearchRunner, RunnerReusableAcrossRuns) {
  auto bars = make_bars(200);
  ParameterSpace space;
  space.add_int_range("period", 5, 15, 5);
  ResearchRunner runner(zero_cost());
  auto a = runner.run_grid(space, bars, interval_gen());
  auto b = runner.run_grid(space, bars, interval_gen());
  ASSERT_TRUE(a.is_ok());
  ASSERT_TRUE(b.is_ok());
  EXPECT_EQ(a.value().compute_result_hash(), b.value().compute_result_hash());
}

TEST(ResearchRunner, RunnerConcurrentCalls) {
  auto bars = make_bars(300);
  ParameterSpace space;
  space.add_grid("fast", {3.0, 5.0, 8.0});
  space.add_grid("slow", {10.0, 20.0, 30.0});
  ResearchRunner runner(zero_cost());
  ResearchPlan plan;
  plan.space = space;
  plan.max_parallelism = 2;
  OptimizationResult r1, r2;
  std::atomic<bool> ok1{false}, ok2{false};
  std::thread t1([&] {
    auto res = runner.run(plan, bars, sma_cross_gen(), &stop_tp_provider());
    if (res.is_ok()) {
      r1 = std::move(res).value();
      ok1 = true;
    }
  });
  std::thread t2([&] {
    auto res = runner.run(plan, bars, sma_cross_gen(), &stop_tp_provider());
    if (res.is_ok()) {
      r2 = std::move(res).value();
      ok2 = true;
    }
  });
  t1.join();
  t2.join();
  ASSERT_TRUE(ok1.load());
  ASSERT_TRUE(ok2.load());
  EXPECT_EQ(r1.compute_result_hash(), r2.compute_result_hash());
}

// ── Name helpers ────────────────────────────────────────────────────────────

TEST(Research, SearchTypeNames) {
  EXPECT_STREQ(search_type_name(SearchType::Grid), "grid");
  EXPECT_STREQ(search_type_name(SearchType::Random), "random");
  EXPECT_STREQ(search_type_name(SearchType::Seeded), "seeded");
}

TEST(Research, OptimizationMetricNames) {
  EXPECT_STREQ(optimization_metric_name(OptimizationMetric::NetProfit),
               "net_profit");
  EXPECT_STREQ(optimization_metric_name(OptimizationMetric::Sharpe), "sharpe");
  EXPECT_STREQ(optimization_metric_name(OptimizationMetric::Sortino), "sortino");
  EXPECT_STREQ(optimization_metric_name(OptimizationMetric::Calmar), "calmar");
  EXPECT_STREQ(optimization_metric_name(OptimizationMetric::MaxDrawdown),
               "max_drawdown");
  EXPECT_STREQ(optimization_metric_name(OptimizationMetric::ProfitFactor),
               "profit_factor");
  EXPECT_STREQ(optimization_metric_name(OptimizationMetric::WinRate), "win_rate");
  EXPECT_STREQ(optimization_metric_name(OptimizationMetric::Expectancy),
               "expectancy");
  EXPECT_STREQ(optimization_metric_name(OptimizationMetric::RecoveryFactor),
               "recovery_factor");
  EXPECT_STREQ(optimization_metric_name(OptimizationMetric::TradeCount),
               "trade_count");
  EXPECT_STREQ(optimization_metric_name(OptimizationMetric::Stability),
               "stability");
}
