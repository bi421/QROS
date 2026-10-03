// Strategy Simulation Kernel — comprehensive unit tests.
//
// Covers: long/short, stop loss, take profit, trailing stop, break-even,
// partial close, commission/spread/slippage, risk%/fixed-lot sizing, ATR
// stops, time stop, daily loss limit, max open positions, session filter,
// statistics, determinism, hashing, edge cases (gaps, same-candle SL/TP,
// zero/huge spread), and large-scale throughput.

#include "quant/strategy/strategy_kernel.h"
#include "quant/strategy/position.h"
#include "quant/strategy/trade_result.h"
#include "quant/strategy/simulation_result.h"

#include <gtest/gtest.h>

#include <chrono>
#include <cmath>
#include <vector>

using namespace quant;
using namespace quant::strategy;

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

StrategySignal open_sig(int64_t bar, TradeSide side = TradeSide::Long) {
  StrategySignal s;
  s.bar_index = bar;
  s.action = SignalAction::Open;
  s.side = side;
  return s;
}

StrategySignal close_sig(int64_t bar, TradeSide side = TradeSide::Long) {
  StrategySignal s;
  s.bar_index = bar;
  s.action = SignalAction::Close;
  s.side = side;
  return s;
}

StrategySignal open_sig_qty(int64_t bar, double qty,
                            TradeSide side = TradeSide::Long) {
  StrategySignal s = open_sig(bar, side);
  s.quantity = qty;
  return s;
}

// Cost-free fixed-lot baseline config (easy hand-computed expectations).
StrategyConfig zero_cost_cfg() {
  StrategyConfig cfg;
  cfg.trade.commission_pct = 0.0;
  cfg.trade.spread_pct = 0.0;
  cfg.trade.slippage_pct = 0.0;
  cfg.trade.sizing = PositionSizing::FixedLot;
  cfg.trade.fixed_lot = 1.0;
  return cfg;
}

SimulationResult run_kernel(const StrategyConfig& cfg,
                            const std::vector<OHLCV>& bars,
                            const std::vector<StrategySignal>& signals,
                            bool hash = true) {
  StrategyKernel k(cfg);
  auto res = k.run(bars, signals, hash);
  if (!res.is_ok()) {
    ADD_FAILURE() << "kernel run failed: " << res.error().message();
    return {};
  }
  return std::move(res).value();
}

} // namespace

// ── Basic behavior ─────────────────────────────────────────────────────────

TEST(StrategyKernel, NoSignalsProducesFlatRun) {
  auto cfg = zero_cost_cfg();
  std::vector<OHLCV> bars = {mk(100, 101, 99, 100, 0), mk(100, 101, 99, 100, 1)};
  auto r = run_kernel(cfg, bars, {});
  EXPECT_EQ(r.trades.size(), 0u);
  EXPECT_EQ(r.stats.total_trades, 0u);
  EXPECT_EQ(r.equity_curve.size(), bars.size());
  EXPECT_EQ(r.drawdown_curve.size(), bars.size());
  EXPECT_EQ(r.signals_processed, 0u);
  EXPECT_EQ(r.signals_opened, 0u);
  EXPECT_DOUBLE_EQ(r.final_equity, 100000.0);
  EXPECT_FALSE(r.input_hash.empty());
  EXPECT_FALSE(r.result_hash.empty());
  EXPECT_EQ(r.result_hash, r.compute_result_hash());
}

TEST(StrategyKernel, OneSignalOpensOneTrade) {
  auto cfg = zero_cost_cfg();
  std::vector<OHLCV> bars = {mk(100, 101, 99, 100, 0), mk(100, 102, 99, 101, 1)};
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  EXPECT_EQ(r.signals_processed, 1u);
  EXPECT_EQ(r.signals_opened, 1u);
  EXPECT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].entry_bar, 1);
  EXPECT_DOUBLE_EQ(r.trades[0].entry_price, 100.0);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::EndOfData);
}

TEST(StrategyKernel, SignalOnFinalBarNeverFills) {
  auto cfg = zero_cost_cfg();
  std::vector<OHLCV> bars = {mk(100, 101, 99, 100, 0), mk(100, 102, 99, 101, 1)};
  auto r = run_kernel(cfg, bars, {open_sig(1)});
  EXPECT_EQ(r.signals_processed, 1u);
  EXPECT_EQ(r.signals_opened, 0u);
  EXPECT_EQ(r.trades.size(), 0u);
}

TEST(StrategyKernel, SignalsSortedIndependentlyOfInputOrder) {
  auto cfg = zero_cost_cfg();
  std::vector<OHLCV> bars;
  for (int64_t i = 0; i < 6; ++i)
    bars.push_back(mk(100, 102, 98, 100 + (i % 3), i));
  auto a = run_kernel(cfg, bars, {open_sig(0), open_sig(2), open_sig(4)});
  auto b = run_kernel(cfg, bars, {open_sig(4), open_sig(0), open_sig(2)});
  EXPECT_EQ(a.input_hash, b.input_hash);
  EXPECT_EQ(a.result_hash, b.result_hash);
  EXPECT_EQ(a.equity_curve, b.equity_curve);
}

TEST(StrategyKernel, ConfigAccessors) {
  auto cfg = zero_cost_cfg();
  cfg.trade.fixed_lot = 7.0;
  StrategyKernel k(cfg);
  EXPECT_DOUBLE_EQ(k.config().trade.fixed_lot, 7.0);
  cfg.trade.fixed_lot = 9.0;
  k.set_config(cfg);
  EXPECT_DOUBLE_EQ(k.config().trade.fixed_lot, 9.0);
}

// ── Validation ─────────────────────────────────────────────────────────────

TEST(StrategyKernel, EmptyBarsRejected) {
  StrategyKernel k(zero_cost_cfg());
  auto r = k.run({}, {});
  EXPECT_TRUE(r.is_err());
  EXPECT_EQ(r.error().code(), ErrorCode::InsufficientData);
}

TEST(StrategyKernel, InvalidCandleRejected) {
  StrategyKernel k(zero_cost_cfg());
  std::vector<OHLCV> bars = {mk(100, 99, 98, 100, 0)}; // high < low
  auto r = k.run(bars, {});
  EXPECT_TRUE(r.is_err());
  EXPECT_EQ(r.error().code(), ErrorCode::InvalidArgument);
}

TEST(StrategyKernel, NonMonotonicTimestampsRejected) {
  StrategyKernel k(zero_cost_cfg());
  std::vector<OHLCV> bars = {mk(100, 101, 99, 100, 5), mk(100, 101, 99, 100, 3)};
  auto r = k.run(bars, {});
  EXPECT_TRUE(r.is_err());
  EXPECT_EQ(r.error().code(), ErrorCode::InvalidArgument);
}

TEST(StrategyKernel, SignalBarIndexOutOfRangeRejected) {
  StrategyKernel k(zero_cost_cfg());
  std::vector<OHLCV> bars = {mk(100, 101, 99, 100, 0), mk(100, 101, 99, 100, 1)};
  auto r = k.run(bars, {open_sig(2)});
  EXPECT_TRUE(r.is_err());
  EXPECT_EQ(r.error().code(), ErrorCode::OutOfBounds);
}

TEST(StrategyKernel, NegativeSignalBarIndexRejected) {
  StrategyKernel k(zero_cost_cfg());
  std::vector<OHLCV> bars = {mk(100, 101, 99, 100, 0), mk(100, 101, 99, 100, 1)};
  auto r = k.run(bars, {open_sig(-1)});
  EXPECT_TRUE(r.is_err());
}

// ── Long / short with SL and TP ────────────────────────────────────────────

TEST(StrategyKernel, LongTakeProfitFillsAtLevel) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 105, 99.5, 104, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::TakeProfit);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 102.0);
  EXPECT_DOUBLE_EQ(r.trades[0].net_pnl, 2.0);
  EXPECT_DOUBLE_EQ(r.trades[0].r_multiple, 1.0);
  EXPECT_EQ(r.trades[0].bars_held, 1);
}

TEST(StrategyKernel, LongStopLossFillsAtLevel) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100.5, 97, 97.5, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::StopLoss);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 98.0);
  EXPECT_DOUBLE_EQ(r.trades[0].net_pnl, -2.0);
  EXPECT_DOUBLE_EQ(r.trades[0].r_multiple, -1.0);
}

TEST(StrategyKernel, ShortTakeProfitFillsAtLevel) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100.3, 97, 98, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0, TradeSide::Short)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].side, TradeSide::Short);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::TakeProfit);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 98.0);
  EXPECT_DOUBLE_EQ(r.trades[0].net_pnl, 2.0);
}

TEST(StrategyKernel, ShortStopLossFillsAtLevel) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 102.5, 99, 101.5, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0, TradeSide::Short)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::StopLoss);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 102.0);
  EXPECT_DOUBLE_EQ(r.trades[0].net_pnl, -2.0);
}

TEST(StrategyKernel, SignalStopOverrideOverridesConfig) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.take_profit = 0.0;
  StrategySignal s = open_sig(0);
  s.has_stop_loss = true;
  s.stop_loss = 95.0; // override config 98 -> 95
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100.3, 94.5, 96, 1),
  };
  auto r = run_kernel(cfg, bars, {s});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 95.0);
  EXPECT_DOUBLE_EQ(r.trades[0].net_pnl, -5.0);
}

// ── Gap handling ───────────────────────────────────────────────────────────

TEST(StrategyKernel, GapThroughStopFillsAtOpen) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(95, 99, 94, 94.5, 1), // gaps below stop 98
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::StopLoss);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 95.0);
  EXPECT_DOUBLE_EQ(r.trades[0].net_pnl, 0.0); // entry = exit = gap open
}

TEST(StrategyKernel, GapThroughTakeProfitFillsAtOpen) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(104, 106, 103, 105, 1), // gaps above TP 102
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::TakeProfit);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 104.0);
  EXPECT_DOUBLE_EQ(r.trades[0].net_pnl, 0.0); // entry = exit = gap open
}

TEST(StrategyKernel, GapDownForShortStopFillsAtOpen) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(104, 105, 103, 104, 1), // gaps up through short stop 102
  };
  auto r = run_kernel(cfg, bars, {open_sig(0, TradeSide::Short)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 104.0);
  EXPECT_DOUBLE_EQ(r.trades[0].net_pnl, 0.0); // entry = exit = gap open
}

TEST(StrategyKernel, SameCandleStopWinsOverTakeProfit) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 105, 97, 101, 1), // both TP 102 and SL 98 inside the candle
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::StopLoss);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 98.0);
  EXPECT_DOUBLE_EQ(r.trades[0].net_pnl, -2.0);
}

TEST(StrategyKernel, SameCandleTimeStopAfterPriceExit) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.max_bars_in_trade = 1;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100.5, 97, 97.5, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::StopLoss); // SL beats time stop
}

// ── Costs ──────────────────────────────────────────────────────────────────

TEST(StrategyKernel, ZeroSpreadZeroCostExactPnL) {
  auto cfg = zero_cost_cfg();
  cfg.trade.spread_pct = 0.0;
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 105, 99.5, 104, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  EXPECT_NEAR(r.trades[0].net_pnl, 2.0, 1e-9);
}

TEST(StrategyKernel, HugeSpreadTurnsProfitIntoLoss) {
  auto cfg = zero_cost_cfg();
  cfg.trade.spread_pct = 0.02; // 1% per side
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 105, 99.5, 104, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_LT(r.trades[0].net_pnl, 0.0); // raw +2.0 becomes a loss after spread
  EXPECT_DOUBLE_EQ(r.trades[0].entry_price, 101.0);
  EXPECT_NEAR(r.trades[0].exit_price, 100.98, 1e-9);
}

TEST(StrategyKernel, SlippageAppliedToEntryAndExit) {
  auto cfg = zero_cost_cfg();
  cfg.trade.slippage_pct = 0.001;
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 105, 99.5, 104, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  EXPECT_NEAR(r.trades[0].entry_price, 100.1, 1e-9);
  EXPECT_NEAR(r.trades[0].exit_price, 101.898, 1e-9);
  EXPECT_NEAR(r.trades[0].net_pnl, 1.798, 1e-9);
}

TEST(StrategyKernel, CommissionAppliedOnEntryAndExit) {
  auto cfg = zero_cost_cfg();
  cfg.trade.commission_pct = 0.001;
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 105, 99.5, 104, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_NEAR(r.trades[0].commission, 0.202, 1e-9); // 0.1 + 0.102
  EXPECT_NEAR(r.trades[0].net_pnl, 1.798, 1e-9);
  EXPECT_NEAR(r.stats.total_commission, 0.202, 1e-9);
}

TEST(StrategyKernel, CommissionPerLotApplied) {
  auto cfg = zero_cost_cfg();
  cfg.trade.commission_per_lot = 0.5;
  cfg.trade.take_profit = 2.0;
  cfg.trade.fixed_lot = 3.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 105, 99.5, 104, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_DOUBLE_EQ(r.trades[0].quantity, 3.0);
  EXPECT_NEAR(r.trades[0].commission, 3.0, 1e-9); // 3 lots * 0.5 * 2 fills
  EXPECT_NEAR(r.trades[0].net_pnl, 6.0 - 3.0, 1e-9);
}

TEST(StrategyKernel, SlippageFieldAccumulatesCosts) {
  auto cfg = zero_cost_cfg();
  cfg.trade.spread_pct = 0.004;
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 105, 99.5, 104, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  EXPECT_NEAR(r.trades[0].slippage, 0.2 + 0.204, 1e-9);
}

// ── Sizing ─────────────────────────────────────────────────────────────────

TEST(StrategyKernel, FixedLotSizing) {
  auto cfg = zero_cost_cfg();
  cfg.trade.sizing = PositionSizing::FixedLot;
  cfg.trade.fixed_lot = 5.0;
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 105, 99.5, 104, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  EXPECT_DOUBLE_EQ(r.trades[0].quantity, 5.0);
  EXPECT_DOUBLE_EQ(r.trades[0].net_pnl, 10.0);
}

TEST(StrategyKernel, RiskPercentSizingScalesWithStopDistance) {
  auto cfg = zero_cost_cfg();
  cfg.trade.sizing = PositionSizing::RiskPercent;
  cfg.trade.risk_percent = 1.0; // risk 1000 on 100k equity
  cfg.trade.stop_loss = 2.0;    // qty = 1000 / 2 = 500
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100.5, 97, 97.5, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_DOUBLE_EQ(r.trades[0].quantity, 500.0);
  EXPECT_NEAR(r.trades[0].net_pnl, -1000.0, 1e-6);
  EXPECT_NEAR(r.trades[0].r_multiple, -1.0, 1e-9);
}

TEST(StrategyKernel, RiskAmountOverride) {
  auto cfg = zero_cost_cfg();
  cfg.trade.sizing = PositionSizing::RiskPercent;
  cfg.trade.risk_amount = 2000.0; // fixed override
  cfg.trade.stop_loss = 2.0;
  StrategySignal s = open_sig(0);
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100.5, 97, 97.5, 1),
  };
  auto r = run_kernel(cfg, bars, {s});
  EXPECT_DOUBLE_EQ(r.trades[0].quantity, 1000.0);
}

TEST(StrategyKernel, SignalRiskAmountOverride) {
  auto cfg = zero_cost_cfg();
  cfg.trade.sizing = PositionSizing::RiskPercent;
  cfg.trade.stop_loss = 2.0;
  StrategySignal s = open_sig(0);
  s.risk_amount = 500.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100.5, 97, 97.5, 1),
  };
  auto r = run_kernel(cfg, bars, {s});
  EXPECT_DOUBLE_EQ(r.trades[0].quantity, 250.0);
}

TEST(StrategyKernel, SignalQuantityDoesNotOverrideSizing) {
  auto cfg = zero_cost_cfg();
  cfg.trade.sizing = PositionSizing::FixedLot;
  cfg.trade.fixed_lot = 2.0;
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 105, 99.5, 104, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig_qty(0, 7.0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_DOUBLE_EQ(r.trades[0].quantity, 2.0);
  EXPECT_DOUBLE_EQ(r.trades[0].net_pnl, 4.0);
}

TEST(StrategyKernel, RiskSizingWithoutStopRejectsEntry) {
  auto cfg = zero_cost_cfg();
  cfg.trade.sizing = PositionSizing::RiskPercent;
  cfg.trade.default_quantity = 4.0;
  cfg.trade.stop_loss = 0.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100, 100, 100, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  EXPECT_EQ(r.trades.size(), 0u);
  EXPECT_EQ(r.signals_opened, 0u);
  EXPECT_EQ(r.signals_ignored, 1u);
}

// ── Trailing stop ──────────────────────────────────────────────────────────

TEST(StrategyKernel, TrailingStopLocksInProfit) {
  auto cfg = zero_cost_cfg();
  cfg.trade.trailing_stop = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 105, 99, 104, 1),
      mk(103.5, 104, 102, 102.5, 2),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::TrailingStop);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 103.0);
  EXPECT_DOUBLE_EQ(r.trades[0].net_pnl, 3.0);
}

TEST(StrategyKernel, TrailingStopRatchetsOnlyUp) {
  auto cfg = zero_cost_cfg();
  cfg.trade.trailing_stop = 1.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 102, 99, 101.5, 1), // arm, stop -> 101
      mk(103.5, 104, 103.2, 103.5, 2), // ratchet stop -> 103
      mk(103, 103, 102, 102, 3),  // low 102 hits stop 103
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::TrailingStop);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 103.0);
  EXPECT_DOUBLE_EQ(r.trades[0].net_pnl, 3.0);
}

TEST(StrategyKernel, TrailingActivationRequiresProfit) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.trailing_stop = 1.0;
  cfg.trade.trailing_activation_pct = 0.5; // needs profit >= 1.0
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100.5, 99.8, 100.3, 1), // profit 0.5 < 1.0, not armed
      mk(100, 103, 99.7, 102.8, 2),   // profit 3.0 >= 1.0, arm + ratchet stop -> 102
      mk(102, 102, 101.5, 101.6, 3),  // low 101.5 hits 102
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::TrailingStop);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 102.0);
  EXPECT_DOUBLE_EQ(r.trades[0].net_pnl, 2.0);
}

TEST(StrategyKernel, TrailingStopOverriddenBySignal) {
  auto cfg = zero_cost_cfg();
  cfg.trade.trailing_stop = 5.0;
  StrategySignal s = open_sig(0);
  s.has_trailing_stop = true;
  s.trailing_stop = 1.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 103, 99.5, 102.5, 1),
      mk(102.5, 102.5, 101.5, 101.8, 2),
  };
  auto r = run_kernel(cfg, bars, {s});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 102.0);
}

// ── Break even ─────────────────────────────────────────────────────────────

TEST(StrategyKernel, BreakEvenMovesStopToEntry) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.break_even_activation_pct = 0.5; // profit >= 1.0
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 101.2, 99.8, 101, 1), // profit 1.2 >= 1.0 -> stop to 100
      mk(100.5, 100.6, 99.2, 99.5, 2), // low 99.2 hits stop 100
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::BreakEven);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 100.0);
}

TEST(StrategyKernel, BreakEvenInactiveWithoutActivation) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.break_even_activation_pct = 0.9; // needs profit >= 1.8
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 101.2, 99.8, 101, 1), // profit 1.2 < 1.8
      mk(100, 100.5, 97.5, 98, 2),  // low hits original stop 98
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::StopLoss);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 98.0);
}

// ── Partial close ──────────────────────────────────────────────────────────

TEST(StrategyKernel, PartialCloseRealizesFractionThenStop) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.partial_close_pct = 0.5;
  cfg.trade.partial_close_target_pct = 1.0; // target 102
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 103, 99.8, 102.5, 1), // partial: 0.5 @ 102
      mk(100, 100.5, 97, 97.5, 2),  // remainder stops @ 98
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_TRUE(r.trades[0].partial_close);
  EXPECT_EQ(r.trades[0].partial_fill_count, 1);
  EXPECT_DOUBLE_EQ(r.trades[0].quantity, 1.0);
  EXPECT_NEAR(r.trades[0].net_pnl, 0.0, 1e-9); // 0.5*(2) + 0.5*(-2)
  EXPECT_NEAR(r.trades[0].avg_exit_price, 100.0, 1e-9);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::StopLoss);
}

TEST(StrategyKernel, PartialCloseGapThroughTarget) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.partial_close_pct = 0.5;
  cfg.trade.partial_close_target_pct = 1.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(104, 105, 103, 104.5, 1), // gaps above target 102 -> fill at open 104
      mk(100, 100.5, 97, 97.5, 2),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_DOUBLE_EQ(r.trades[0].avg_exit_price, 101.0); // 0.5@104 + 0.5@98
  EXPECT_NEAR(r.trades[0].net_pnl, -3.0, 1e-9); // 0.5*(104-104) + 0.5*(98-104)
}

TEST(StrategyKernel, PartialCloseOffWhenFractionZero) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.take_profit = 3.0;
  cfg.trade.partial_close_pct = 0.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 105, 99.8, 104, 1), // TP 103
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_FALSE(r.trades[0].partial_close);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::TakeProfit);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 103.0);
}

// ── Time stop ──────────────────────────────────────────────────────────────

TEST(StrategyKernel, TimeStopClosesAfterMaxBars) {
  auto cfg = zero_cost_cfg();
  cfg.trade.max_bars_in_trade = 3;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 101, 99, 100.5, 1),
      mk(100.5, 101.5, 99.5, 101, 2),
      mk(101, 102, 100, 101.5, 3),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::TimeStop);
  EXPECT_EQ(r.trades[0].bars_held, 3);
  EXPECT_EQ(r.trades[0].exit_bar, 3);
}

TEST(StrategyKernel, TimeStopZeroDisables) {
  auto cfg = zero_cost_cfg();
  cfg.trade.max_bars_in_trade = 0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 101, 99, 100.5, 1),
      mk(100.5, 101.5, 99.5, 101, 2),
      mk(101, 102, 100, 101.5, 3),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::EndOfData);
}

// ── ATR stops ──────────────────────────────────────────────────────────────

TEST(StrategyKernel, AtrStopLevelsFromTrueRange) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_type = StopType::ATR;
  cfg.trade.atr_period = 2;
  cfg.trade.atr_sl_multiplier = 1.5;
  // TR constant 2 -> ATR 2 -> stop distance 3 -> stop level 98 (101 - 3)
  std::vector<OHLCV> bars = {
      mk(100, 101, 99, 101, 0),
      mk(100, 101, 99, 101, 1),
      mk(100, 101, 99, 101, 2), // signal here
      mk(100, 100.5, 96.5, 97.5, 3), // low 96.5 hits stop 98
  };
  auto r = run_kernel(cfg, bars, {open_sig(2)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::StopLoss);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 98.0);
}

TEST(StrategyKernel, AtrTakeProfitMultiplier) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_type = StopType::ATR;
  cfg.trade.atr_period = 2;
  cfg.trade.atr_tp_multiplier = 2.0;
  // ATR 2 -> TP distance 4 -> TP level 105 (101 + 4)
  std::vector<OHLCV> bars = {
      mk(100, 101, 99, 101, 0),
      mk(100, 101, 99, 101, 1),
      mk(100, 101, 99, 101, 2),
      mk(100, 105, 99.5, 104.5, 3),
  };
  auto r = run_kernel(cfg, bars, {open_sig(2)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::TakeProfit);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 105.0);
}

TEST(StrategyKernel, AtrTrailingStop) {
  auto cfg = zero_cost_cfg();
  cfg.trade.atr_trailing_multiplier = 1.0; // ATR 2 -> trailing 2
  std::vector<OHLCV> bars = {
      mk(100, 101, 99, 101, 0),
      mk(100, 101, 99, 101, 1),
      mk(100, 101, 99, 101, 2),
      mk(100, 106, 99.5, 105.5, 3), // arm, ratchet -> stop 104
      mk(104.5, 105, 103, 103.5, 4), // low 103 hits 104
  };
  auto r = run_kernel(cfg, bars, {open_sig(2)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::TrailingStop);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 104.0);
}

// ── Risk limits ────────────────────────────────────────────────────────────

TEST(StrategyKernel, DailyLossLimitBlocksNewEntries) {
  auto cfg = zero_cost_cfg();
  cfg.trade.sizing = PositionSizing::RiskPercent;
  cfg.trade.risk_percent = 2.0;
  cfg.trade.stop_loss = 2.0;
  cfg.risk.daily_loss_limit_pct = 1.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100.5, 97, 97.5, 1), // -2% loss -> breach 1%
      mk(100, 100.5, 97, 97.5, 2), // entry attempt blocked
      mk(100, 100, 100, 100, 3),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0), open_sig(1)});
  EXPECT_EQ(r.signals_opened, 1u);
  EXPECT_EQ(r.signals_ignored, 1u);
  EXPECT_EQ(r.trades.size(), 1u);
}

TEST(StrategyKernel, DailyLossLimitCircuitBreakerClosesPositions) {
  auto cfg = zero_cost_cfg();
  cfg.trade.sizing = PositionSizing::RiskPercent;
  cfg.trade.risk_percent = 2.0;
  cfg.trade.default_quantity = 500.0; // no stop -> default size; 500 * 4 = -2%
  cfg.risk.daily_loss_limit_pct = 1.0;
  // No stop: position bleeds to -2% -> breach triggers forced close.
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100, 96, 96, 1), // unrealized -2%
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::DailyLossLimit);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 96.0);
}

TEST(StrategyKernel, DailyLossLimitResetsNextDay) {
  auto cfg = zero_cost_cfg();
  cfg.trade.sizing = PositionSizing::RiskPercent;
  cfg.trade.risk_percent = 1.0;
  cfg.trade.stop_loss = 2.0;
  cfg.risk.daily_loss_limit_pct = 0.5;
  // Day 1: one big loss breaches. Day 2 (next day key): entries allowed again.
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 60 * 9),      // day0
      mk(100, 100.5, 97, 97.5, 60 * 10),   // loss, breach
      mk(100, 100.5, 97, 97.5, 60 * 11),   // blocked
      mk(100, 100, 100, 100, 60 * 24 * 2 + 60 * 9), // day1 (2 days later)
      mk(100, 100.5, 97, 97.5, 60 * 24 * 2 + 60 * 10),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0), open_sig(2), open_sig(3)});
  EXPECT_EQ(r.signals_opened, 2u);
  EXPECT_EQ(r.signals_ignored, 1u);
  EXPECT_EQ(r.trades.size(), 2u);
}

TEST(StrategyKernel, MaxOpenPositionsCapsEntries) {
  auto cfg = zero_cost_cfg();
  cfg.risk.max_open_positions = 1;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100, 100, 100, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0), open_sig(0)});
  EXPECT_EQ(r.signals_opened, 1u);
  EXPECT_EQ(r.signals_ignored, 1u);
}

TEST(StrategyKernel, MaxTradesPerDayLimitsOpens) {
  auto cfg = zero_cost_cfg();
  cfg.risk.max_trades_per_day = 2;
  std::vector<OHLCV> bars;
  for (int64_t i = 0; i < 8; ++i) bars.push_back(mk(100, 100, 100, 100, i));
  // Open, open, open -> first two fill at bars 1,2; third at bar 3 blocked.
  auto r = run_kernel(cfg, bars, {open_sig(0), open_sig(1), open_sig(2)});
  EXPECT_EQ(r.signals_opened, 2u);
  EXPECT_EQ(r.signals_ignored, 1u);
}

TEST(StrategyKernel, AllowLongDisabledSkipsLong) {
  auto cfg = zero_cost_cfg();
  cfg.trade.allow_long = false;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100, 100, 100, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  EXPECT_EQ(r.signals_opened, 0u);
  EXPECT_EQ(r.signals_ignored, 1u);
}

TEST(StrategyKernel, AllowShortDisabledSkipsShort) {
  auto cfg = zero_cost_cfg();
  cfg.trade.allow_short = false;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100, 100, 100, 1),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0, TradeSide::Short)});
  EXPECT_EQ(r.signals_opened, 0u);
  EXPECT_EQ(r.signals_ignored, 1u);
}

// ── Session filter ─────────────────────────────────────────────────────────

TEST(StrategyKernel, SessionFilterBlocksOutsideHours) {
  auto cfg = zero_cost_cfg();
  cfg.risk.session.enabled = true;
  cfg.risk.session.utc_start_hour = 8;
  cfg.risk.session.utc_end_hour = 16;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 9 * 60),    // hour 9 (allowed)
      mk(100, 100, 100, 100, 20 * 60),   // hour 20 (blocked)
      mk(100, 100, 100, 100, (24 + 9) * 60), // hour 9 next day (allowed)
  };
  // signal on bar0 -> fills bar1 (hour 20) -> blocked
  // signal on bar1 -> fills bar2 (next day hour 9) -> allowed
  auto r = run_kernel(cfg, bars, {open_sig(0), open_sig(1)});
  EXPECT_EQ(r.signals_opened, 1u);
  EXPECT_EQ(r.signals_ignored, 1u);
}

TEST(StrategyKernel, SessionCloseOnEndClosesPositions) {
  auto cfg = zero_cost_cfg();
  cfg.risk.session.enabled = true;
  cfg.risk.session.utc_start_hour = 8;
  cfg.risk.session.utc_end_hour = 15;
  cfg.risk.close_on_session_end = true;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 14 * 60), // in session
      mk(100, 100, 100, 100, 15 * 60), // in session (open fills here)
      mk(100, 100, 100, 100, 16 * 60), // out of session -> close at open
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::SessionClose);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 100.0);
}

TEST(StrategyKernel, SessionFilterWrapsPastMidnight) {
  SessionFilter sf;
  sf.enabled = true;
  sf.utc_start_hour = 22;
  sf.utc_end_hour = 2;
  EXPECT_TRUE(sf.allows_hour(23));
  EXPECT_TRUE(sf.allows_hour(1));
  EXPECT_FALSE(sf.allows_hour(12));
}

TEST(StrategyKernel, SessionFilterWeekdayGating) {
  SessionFilter sf;
  sf.enabled = true;
  sf.allow_saturday = false;
  EXPECT_TRUE(sf.allows_weekday(1)); // Monday
  EXPECT_FALSE(sf.allows_weekday(6)); // Saturday
  EXPECT_TRUE(sf.allows_weekday(0)); // Sunday (allowed by default)
}

// ── Signal actions ─────────────────────────────────────────────────────────

TEST(StrategyKernel, CloseClosesMostRecentPositionOfSide) {
  auto cfg = zero_cost_cfg();
  std::vector<OHLCV> bars;
  for (int64_t i = 0; i < 6; ++i) bars.push_back(mk(100, 100, 100, 100, i));
  auto r = run_kernel(cfg, bars, {open_sig(0), open_sig(0), close_sig(1), close_sig(2)});
  ASSERT_EQ(r.trades.size(), 2u);
  EXPECT_EQ(r.trades[0].trade_id, 2); // most recent closed first
  EXPECT_EQ(r.trades[1].trade_id, 1);
}

TEST(StrategyKernel, CloseWithNoPositionIgnored) {
  auto cfg = zero_cost_cfg();
  std::vector<OHLCV> bars;
  for (int64_t i = 0; i < 4; ++i) bars.push_back(mk(100, 100, 100, 100, i));
  auto r = run_kernel(cfg, bars, {close_sig(0)});
  EXPECT_EQ(r.signals_ignored, 1u);
  EXPECT_EQ(r.trades.size(), 0u);
}

TEST(StrategyKernel, CloseAllClosesEveryPosition) {
  auto cfg = zero_cost_cfg();
  std::vector<OHLCV> bars;
  for (int64_t i = 0; i < 6; ++i) bars.push_back(mk(100, 100, 100, 100, i));
  StrategySignal all;
  all.bar_index = 2;
  all.action = SignalAction::CloseAll;
  auto r = run_kernel(cfg, bars, {open_sig(0), open_sig(0), open_sig(1), all});
  ASSERT_EQ(r.trades.size(), 3u);
  for (const auto& t : r.trades) {
    EXPECT_EQ(t.exit_reason, ExitReason::Signal);
    EXPECT_EQ(t.exit_bar, 3);
  }
}

TEST(StrategyKernel, ModifyUpdatesStopLoss) {
  auto cfg = zero_cost_cfg();
  StrategySignal s = open_sig(0);
  s.quantity = 1.0;
  StrategySignal m = open_sig(1);
  m.action = SignalAction::Modify;
  m.has_stop_loss = true;
  m.stop_loss = 95.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 101, 99, 100.5, 1),
      mk(100, 100.5, 94.5, 95, 2), // hits modified stop 95
  };
  auto r = run_kernel(cfg, bars, {s, m});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_EQ(r.trades[0].exit_reason, ExitReason::StopLoss);
  EXPECT_DOUBLE_EQ(r.trades[0].exit_price, 95.0);
  EXPECT_DOUBLE_EQ(r.trades[0].net_pnl, -5.0);
}

TEST(StrategyKernel, ModifyWithoutPositionIgnored) {
  auto cfg = zero_cost_cfg();
  StrategySignal m = open_sig(0);
  m.action = SignalAction::Modify;
  m.has_stop_loss = true;
  m.stop_loss = 95.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100, 100, 100, 1),
  };
  auto r = run_kernel(cfg, bars, {m});
  EXPECT_EQ(r.signals_ignored, 1u);
  EXPECT_EQ(r.trades.size(), 0u);
}

TEST(StrategyKernel, NoneActionIsNoOp) {
  auto cfg = zero_cost_cfg();
  StrategySignal n = open_sig(0);
  n.action = SignalAction::None;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100, 100, 100, 1),
  };
  auto r = run_kernel(cfg, bars, {n});
  EXPECT_EQ(r.signals_opened, 0u);
  EXPECT_EQ(r.trades.size(), 0u);
}

// ── Statistics ─────────────────────────────────────────────────────────────

TEST(StrategyKernel, StatsMatchHandComputedValues) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 1.0;
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),  // L1 signal
      mk(100, 102.5, 99.8, 102, 1),  // L1 TP +2
      mk(100, 100.4, 99, 100, 2),   // L2 signal (close 100 -> stop 99)
      mk(100, 100.4, 98.5, 99, 3),  // L2 SL -1
      mk(100, 100, 100, 100, 4),     // S3 signal
      mk(100, 100.3, 97.5, 98, 5),   // S3 TP +2
      mk(100, 100, 100, 100, 6),     // S4 signal
      mk(100, 101.2, 99.8, 100.5, 7),// S4 SL -1
  };
  auto r = run_kernel(cfg, bars,
                      {open_sig(0), open_sig(2), open_sig(4, TradeSide::Short),
                       open_sig(6, TradeSide::Short)});
  const auto& s = r.stats;
  ASSERT_EQ(s.total_trades, 4u);
  EXPECT_EQ(s.winning_trades, 2u);
  EXPECT_EQ(s.losing_trades, 2u);
  EXPECT_DOUBLE_EQ(s.win_rate, 50.0);
  EXPECT_DOUBLE_EQ(s.average_win, 2.0);
  EXPECT_DOUBLE_EQ(s.average_loss, -1.0);
  EXPECT_DOUBLE_EQ(s.average_rr, 2.0);
  EXPECT_DOUBLE_EQ(s.gross_profit, 4.0);
  EXPECT_DOUBLE_EQ(s.gross_loss, 2.0);
  EXPECT_DOUBLE_EQ(s.profit_factor, 2.0);
  EXPECT_DOUBLE_EQ(s.expectancy, 0.5);
  EXPECT_DOUBLE_EQ(s.net_profit, 2.0);
  EXPECT_EQ(s.max_consecutive_wins, 1u);
  EXPECT_EQ(s.max_consecutive_losses, 1u);
  EXPECT_NEAR(s.recovery_factor, 2.0, 1e-9);
  EXPECT_FALSE(std::isnan(s.sharpe));
  EXPECT_FALSE(std::isnan(s.sortino));
  EXPECT_GT(s.ulcer_index, 0.0);
  EXPECT_DOUBLE_EQ(r.final_equity, 100002.0);
  EXPECT_NEAR(s.total_return_pct, 0.002, 1e-9);
}

TEST(StrategyKernel, AllWinningTradesInfiniteProfitFactor) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 105, 99.5, 100, 1),
      mk(100, 105, 99.5, 100, 2),
  };
  auto r = run_kernel(cfg, bars, {open_sig(0), open_sig(1)});
  EXPECT_EQ(r.stats.winning_trades, 2u);
  EXPECT_DOUBLE_EQ(r.stats.win_rate, 100.0);
  EXPECT_TRUE(std::isinf(r.stats.profit_factor));
  EXPECT_TRUE(std::isinf(r.stats.average_rr));
}

TEST(StrategyKernel, ConsecutiveLossStreakTracked) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 1.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100.3, 98.4, 98.6, 1),  // L1 -1
      mk(100, 100, 100, 100, 2),
      mk(100, 100.3, 98.4, 98.6, 3),  // L2 -1
      mk(100, 100, 100, 100, 4),
      mk(100, 100.3, 98.4, 98.6, 5),  // L3 -1
  };
  auto r = run_kernel(cfg, bars, {open_sig(0), open_sig(2), open_sig(4)});
  EXPECT_EQ(r.stats.max_consecutive_losses, 3u);
  EXPECT_EQ(r.stats.losing_trades, 3u);
  EXPECT_EQ(r.stats.winning_trades, 0u);
}

TEST(StrategyKernel, EquityCurveMatchesCashAccounting) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 105, 99.5, 100, 1), // +2
      mk(100, 105, 99.5, 100, 2), // +2
  };
  auto r = run_kernel(cfg, bars, {open_sig(0), open_sig(1)});
  EXPECT_EQ(r.equity_curve.size(), 3u);
  EXPECT_DOUBLE_EQ(r.equity_curve[0], 100000.0);
  EXPECT_DOUBLE_EQ(r.equity_curve[1], 100002.0);
  EXPECT_DOUBLE_EQ(r.equity_curve[2], 100004.0);
  EXPECT_DOUBLE_EQ(r.final_equity, 100004.0);
}

TEST(StrategyKernel, PeriodReturnsPopulated) {
  auto cfg = zero_cost_cfg();
  cfg.trade.take_profit = 1.0;
  std::vector<OHLCV> bars;
  // Daily bars spanning 2024-01-01 .. mid 2025 (UTC).
  TimePoint start = TimePoint() + std::chrono::hours(24) * 19723; // 2024-01-01
  for (int64_t i = 0; i < 500; ++i) {
    OHLCV b;
    b.timestamp = start + std::chrono::hours(24 * i);
    b.open = 100; b.high = 101; b.low = 99; b.close = 100; b.volume = 1000;
    bars.push_back(b);
  }
  auto r = run_kernel(cfg, bars, {});
  EXPECT_GE(r.yearly_returns.size(), 2u);
  EXPECT_EQ(r.yearly_returns[0].label, "2024");
  EXPECT_GT(r.monthly_returns.size(), 12u);
  for (const auto& m : r.monthly_returns) {
    EXPECT_EQ(m.label.size(), 7u);
    EXPECT_FALSE(std::isnan(m.return_pct));
  }
}

TEST(StrategyKernel, MaxDrawdownTracked) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100.3, 97, 97.5, 1), // L1 -2
      mk(100, 100, 100, 100, 2),
      mk(100, 105, 99.5, 104, 3),  // L2 +2 -> new peak
      mk(100, 100, 100, 100, 4),
      mk(100, 100.3, 97, 97.5, 5), // L3 -2
  };
  auto r = run_kernel(cfg, bars, {open_sig(0), open_sig(2), open_sig(4)});
  EXPECT_GT(r.stats.max_drawdown_pct, 0.0);
  EXPECT_GT(r.stats.max_drawdown, 0.0);
  // drawdown_curve has one entry per bar and stays non-negative
  EXPECT_EQ(r.drawdown_curve.size(), bars.size());
  for (double dd : r.drawdown_curve) EXPECT_GE(dd, 0.0);
}

// ── Determinism & hashing ──────────────────────────────────────────────────

TEST(StrategyKernel, DeterministicRunsProduceIdenticalResults) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.take_profit = 2.0;
  cfg.trade.trailing_stop = 3.0;
  std::vector<OHLCV> bars;
  for (int64_t i = 0; i < 60; ++i)
    bars.push_back(mk(100, 101 + (i % 4), 99 - (i % 3), 100.5, i));
  std::vector<StrategySignal> sigs;
  for (int64_t i = 0; i < 20; ++i) {
    sigs.push_back(open_sig(2 * i));
    sigs.push_back(close_sig(2 * i + 1));
  }
  StrategyKernel k(cfg);
  auto ra = k.run(bars, sigs);
  auto rb = k.run(bars, sigs);
  ASSERT_TRUE(ra.is_ok());
  ASSERT_TRUE(rb.is_ok());
  const auto& a = ra.value();
  const auto& b = rb.value();
  EXPECT_EQ(a.equity_curve, b.equity_curve);
  EXPECT_EQ(a.drawdown_curve, b.drawdown_curve);
  ASSERT_EQ(a.trades.size(), b.trades.size());
  for (size_t i = 0; i < a.trades.size(); ++i) {
    EXPECT_EQ(a.trades[i].net_pnl, b.trades[i].net_pnl);
    EXPECT_EQ(a.trades[i].exit_price, b.trades[i].exit_price);
    EXPECT_EQ(a.trades[i].r_multiple, b.trades[i].r_multiple);
    EXPECT_EQ(a.trades[i].exit_reason, b.trades[i].exit_reason);
  }
  EXPECT_EQ(a.input_hash, b.input_hash);
  EXPECT_EQ(a.result_hash, b.result_hash);
  EXPECT_EQ(a.result_hash, a.compute_result_hash());
}

TEST(StrategyKernel, InputHashSensitiveToConfig) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  std::vector<OHLCV> bars = {mk(100, 101, 99, 100, 0), mk(100, 101, 99, 100, 1)};
  auto a = run_kernel(cfg, bars, {});
  auto cfg2 = cfg;
  cfg2.trade.risk_percent = 3.0;
  auto b = run_kernel(cfg2, bars, {});
  EXPECT_NE(a.input_hash, b.input_hash);
  EXPECT_NE(a.result_hash, b.result_hash);
}

TEST(StrategyKernel, InputHashSensitiveToBarsAndSignals) {
  auto cfg = zero_cost_cfg();
  std::vector<OHLCV> bars = {mk(100, 101, 99, 100, 0), mk(100, 101, 99, 100, 1)};
  auto a = run_kernel(cfg, bars, {open_sig(0)});
  auto b = run_kernel(cfg, bars, {});
  auto c = run_kernel(cfg, {mk(101, 102, 100, 101, 0), mk(101, 102, 100, 101, 1)}, {});
  EXPECT_NE(a.input_hash, b.input_hash);
  EXPECT_NE(b.input_hash, c.input_hash);
}

TEST(StrategyKernel, HashDisabledSkipsComputation) {
  auto cfg = zero_cost_cfg();
  std::vector<OHLCV> bars = {mk(100, 101, 99, 100, 0), mk(100, 101, 99, 100, 1)};
  auto r = run_kernel(cfg, bars, {open_sig(0)}, /*hash=*/false);
  EXPECT_TRUE(r.input_hash.empty());
  EXPECT_TRUE(r.result_hash.empty());
  EXPECT_EQ(r.trades.size(), 1u);
}

TEST(StrategyKernel, ResultHashIsStableAcrossInstances) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.take_profit = 2.0;
  std::vector<OHLCV> bars;
  for (int64_t i = 0; i < 30; ++i)
    bars.push_back(mk(100, 102, 98, 100, i));
  std::vector<StrategySignal> sigs;
  for (int64_t i = 0; i < 10; ++i) sigs.push_back(open_sig(2 * i));
  auto a = run_kernel(cfg, bars, sigs);
  auto b = run_kernel(cfg, bars, sigs);
  EXPECT_EQ(a.input_hash, b.input_hash);
  EXPECT_EQ(a.result_hash, b.result_hash);
}

// ── Position & TradeResult helpers ─────────────────────────────────────────

TEST(Position, PnLHelpers) {
  OpenPosition p;
  p.side = TradeSide::Long;
  p.open_raw = 100.0;
  p.entry_price = 100.2; // costs
  p.quantity = 10.0;
  EXPECT_DOUBLE_EQ(p.value_per_unit(105.0), 5.0);
  EXPECT_DOUBLE_EQ(p.unrealized_pnl(105.0), 48.0);
  EXPECT_FALSE(p.stop_hit(101.0, 99.0)); // no stop set -> never hit
  // set a stop and recheck
  p.stop_loss = 98.0;
  EXPECT_TRUE(p.stop_hit(100.0, 97.5));
  EXPECT_FALSE(p.stop_hit(99.0, 98.5));
  EXPECT_DOUBLE_EQ(p.stop_fill(95.0), 95.0); // gap -> open
  EXPECT_DOUBLE_EQ(p.stop_fill(100.0), 98.0);
  p.take_profit = 105.0;
  EXPECT_TRUE(p.tp_hit(106.0, 99.0));
  EXPECT_DOUBLE_EQ(p.tp_fill(99.0), 105.0);
  EXPECT_DOUBLE_EQ(p.tp_fill(107.0), 107.0); // gap up -> open
}

TEST(Position, ShortPnLHelpers) {
  OpenPosition p;
  p.side = TradeSide::Short;
  p.open_raw = 100.0;
  p.entry_price = 99.8;
  p.quantity = 4.0;
  EXPECT_DOUBLE_EQ(p.value_per_unit(95.0), 5.0);
  EXPECT_DOUBLE_EQ(p.unrealized_pnl(95.0), 19.2);
  p.stop_loss = 102.0;
  EXPECT_TRUE(p.stop_hit(102.5, 99.0));
  EXPECT_DOUBLE_EQ(p.stop_fill(104.0), 104.0);
  EXPECT_DOUBLE_EQ(p.stop_fill(100.0), 102.0);
}

TEST(Position, MfeMaeUpdate) {
  OpenPosition p;
  p.side = TradeSide::Long;
  p.open_raw = 100.0;
  p.update_mfe_mae(103.0, 98.5);
  EXPECT_DOUBLE_EQ(p.mfe, 3.0);
  EXPECT_DOUBLE_EQ(p.mae, -1.5);
  p.update_mfe_mae(101.0, 97.0);
  EXPECT_DOUBLE_EQ(p.mfe, 3.0);
  EXPECT_DOUBLE_EQ(p.mae, -3.0);
}

TEST(Position, ShortMfeMaeUpdate) {
  OpenPosition p;
  p.side = TradeSide::Short;
  p.open_raw = 100.0;
  p.update_mfe_mae(102.0, 97.0);
  EXPECT_DOUBLE_EQ(p.mfe, 3.0);
  EXPECT_DOUBLE_EQ(p.mae, -2.0);
}

TEST(Position, MoveStopToBreakEven) {
  OpenPosition p;
  p.side = TradeSide::Long;
  p.open_raw = 100.0;
  p.stop_loss = 98.0;
  p.move_stop_to_break_even();
  EXPECT_DOUBLE_EQ(p.stop_loss, 100.0);
  EXPECT_TRUE(p.break_even_moved);
}

TEST(Position, RatchetTrailingRatchetsUpForLong) {
  OpenPosition p;
  p.side = TradeSide::Long;
  p.trailing_active = true;
  p.trailing_distance = 2.0;
  p.stop_loss = 100.0;
  p.ratchet_trailing(105.0);
  EXPECT_DOUBLE_EQ(p.stop_loss, 103.0);
  p.ratchet_trailing(104.0); // no ratchet down
  EXPECT_DOUBLE_EQ(p.stop_loss, 103.0);
}

TEST(Position, RatchetTrailingRatchetsDownForShort) {
  OpenPosition p;
  p.side = TradeSide::Short;
  p.trailing_active = true;
  p.trailing_distance = 2.0;
  p.stop_loss = 103.0;
  p.ratchet_trailing(99.0);
  EXPECT_DOUBLE_EQ(p.stop_loss, 101.0);
  p.ratchet_trailing(101.0);
  EXPECT_DOUBLE_EQ(p.stop_loss, 101.0);
}

TEST(Position, RatchetRequiresActiveTrailing) {
  OpenPosition p;
  p.side = TradeSide::Long;
  p.trailing_distance = 2.0;
  p.stop_loss = 100.0;
  p.ratchet_trailing(106.0);
  EXPECT_DOUBLE_EQ(p.stop_loss, 100.0); // not active -> unchanged
}

TEST(TradeResult, ClassificationHelpers) {
  TradeResult t;
  t.net_pnl = 3.0;
  EXPECT_TRUE(t.is_profitable());
  EXPECT_FALSE(t.is_loss());
  t.net_pnl = -1.5;
  EXPECT_TRUE(t.is_loss());
  t.net_pnl = 0.0;
  EXPECT_TRUE(t.is_breakeven());
  t.net_pnl_pct = 1.25;
  EXPECT_DOUBLE_EQ(t.profit_loss_percent(), 1.25);
}

TEST(TradeResult, SummaryProducesReadableText) {
  TradeResult t;
  t.trade_id = 42;
  t.side = TradeSide::Long;
  t.entry_price = 100.0;
  t.exit_price = 105.0;
  t.entry_bar = 3;
  t.exit_bar = 9;
  t.net_pnl = 5.0;
  t.r_multiple = 1.0;
  t.exit_reason = ExitReason::TakeProfit;
  auto s = t.summary();
  EXPECT_NE(s.find("Trade #42"), std::string::npos);
  EXPECT_NE(s.find("TakeProfit"), std::string::npos);
  EXPECT_NE(s.find("Long"), std::string::npos);
}

TEST(TradeResult, ExitReasonNames) {
  EXPECT_STREQ(exit_reason_name(ExitReason::Signal), "Signal");
  EXPECT_STREQ(exit_reason_name(ExitReason::StopLoss), "StopLoss");
  EXPECT_STREQ(exit_reason_name(ExitReason::TakeProfit), "TakeProfit");
  EXPECT_STREQ(exit_reason_name(ExitReason::TrailingStop), "TrailingStop");
  EXPECT_STREQ(exit_reason_name(ExitReason::BreakEven), "BreakEven");
  EXPECT_STREQ(exit_reason_name(ExitReason::TimeStop), "TimeStop");
  EXPECT_STREQ(exit_reason_name(ExitReason::DailyLossLimit), "DailyLossLimit");
  EXPECT_STREQ(exit_reason_name(ExitReason::SessionClose), "SessionClose");
  EXPECT_STREQ(exit_reason_name(ExitReason::EndOfData), "EndOfData");
}

TEST(StrategySignal, NameHelpers) {
  EXPECT_STREQ(action_name(SignalAction::Open), "Open");
  EXPECT_STREQ(action_name(SignalAction::Close), "Close");
  EXPECT_STREQ(action_name(SignalAction::CloseAll), "CloseAll");
  EXPECT_STREQ(action_name(SignalAction::Modify), "Modify");
  EXPECT_STREQ(side_name(TradeSide::Long), "Long");
  EXPECT_STREQ(side_name(TradeSide::Short), "Short");
}

// ── Large-scale ────────────────────────────────────────────────────────────

TEST(StrategyKernel, MillionSignalsThroughput) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  cfg.trade.take_profit = 3.0;
  constexpr int64_t kSignals = 1'000'000;
  constexpr int64_t kBars = 100'000;
  std::vector<OHLCV> bars;
  bars.reserve(kBars);
  for (int64_t i = 0; i < kBars; ++i)
    bars.push_back(mk(100, 103, 97, 100, i));
  std::vector<StrategySignal> sigs;
  sigs.reserve(kSignals);
  for (int64_t i = 0; i < kSignals; ++i) {
    StrategySignal s;
    s.bar_index = i % (kBars - 1);
    s.action = (i % 2 == 0) ? SignalAction::Open : SignalAction::Close;
    s.side = TradeSide::Long;
    sigs.push_back(s);
  }
  auto r = run_kernel(cfg, bars, sigs, /*hash=*/false);
  EXPECT_EQ(r.bars_processed, kBars);
  EXPECT_EQ(r.signals_processed, kSignals);
  EXPECT_GT(r.trades.size(), 400'000u);
  EXPECT_EQ(r.equity_curve.size(), bars.size());
}

TEST(StrategyKernel, MillionBarEquityCurve) {
  auto cfg = zero_cost_cfg();
  constexpr int64_t k = 1'000'000;
  std::vector<OHLCV> bars;
  bars.reserve(k);
  for (int64_t i = 0; i < k; ++i)
    bars.push_back(mk(100, 100, 100, 100, i));
  auto r = run_kernel(cfg, bars, {open_sig(0)}, /*hash=*/false);
  EXPECT_EQ(r.bars_processed, static_cast<size_t>(k));
  EXPECT_EQ(r.equity_curve.size(), static_cast<size_t>(k));
  EXPECT_EQ(r.drawdown_curve.size(), static_cast<size_t>(k));
  EXPECT_EQ(r.trades.size(), 1u); // EndOfData liquidation
  EXPECT_DOUBLE_EQ(r.final_equity, 100000.0);
}

TEST(StrategyKernel, ManyOpenPositionsManagedPerBar) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 2.0;
  constexpr int64_t k = 20'000;
  std::vector<OHLCV> bars;
  bars.reserve(k);
  for (int64_t i = 0; i < k; ++i)
    bars.push_back(mk(100, 100.4, 97.4, 98, i));
  std::vector<StrategySignal> sigs;
  for (int64_t i = 0; i < 500; ++i) sigs.push_back(open_sig(0));
  auto r = run_kernel(cfg, bars, sigs, /*hash=*/false);
  // Each of the 500 opens stops at 98 on bar 1.
  EXPECT_EQ(r.signals_opened, 500u);
  EXPECT_EQ(r.trades.size(), 500u);
  EXPECT_EQ(r.stats.total_trades, 500u);
}

// ── Equity / drawdown edge cases ───────────────────────────────────────────

TEST(StrategyKernel, EquityNeverNegativeAccounting) {
  auto cfg = zero_cost_cfg();
  cfg.trade.stop_loss = 0.0;
  cfg.trade.sizing = PositionSizing::RiskPercent;
  cfg.trade.risk_percent = 5.0;
  std::vector<OHLCV> bars = {
      mk(100, 100, 100, 100, 0),
      mk(100, 100, 60, 60, 1), // deep adverse move, no stop
  };
  auto r = run_kernel(cfg, bars, {open_sig(0)});
  ASSERT_EQ(r.trades.size(), 1u);
  EXPECT_LT(r.trades[0].net_pnl, 0.0);
  // final equity = initial + net (equity is never guaranteed positive for a
  // levered loss, but accounting stays consistent)
  EXPECT_DOUBLE_EQ(r.final_equity, 100000.0 + r.trades[0].net_pnl);
  EXPECT_NEAR(r.stats.net_profit, r.trades[0].net_pnl, 1e-9);
}
