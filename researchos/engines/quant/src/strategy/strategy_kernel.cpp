#include "quant/strategy/strategy_kernel.h"
#include "quant/strategy/position.h"
#include "strategy_internal.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <utility>

namespace quant {
namespace strategy {

namespace {

// ── Per-run state ──────────────────────────────────────────────────────────

struct StopPlan {
  double stop_distance{0.0};
  double stop_level{0.0};
  double tp_distance{0.0};
  double tp_level{0.0};
  double trailing_distance{0.0};
  double activation_distance{0.0};
  double break_even_activation{0.0};
  double partial_target{0.0};
};

struct Context {
  const std::vector<OHLCV>& bars;
  const StrategyConfig& cfg;
  const std::vector<double>& atr; // empty when ATR is not required

  SimulationResult* result{nullptr};
  double cash{0.0};
  double current_equity{0.0};
  std::vector<OpenPosition> positions;
  std::vector<const StrategySignal*> pending;
  int64_t next_id{1};
  size_t signals_opened{0};
  size_t signals_ignored{0};

  int64_t last_day_key{0};
  double daily_start_equity{0.0};
  size_t daily_trades{0};
  bool loss_limit_hit{false};
  bool prev_in_session{false};
  bool prev_session_known{false};
};

// ── ATR ────────────────────────────────────────────────────────────────────

std::vector<double> compute_atr(const std::vector<OHLCV>& bars, int period) {
  period = std::max(1, period);
  std::vector<double> atr(bars.size(), 0.0);
  std::vector<double> tr(bars.size(), 0.0);
  double sum = 0.0;
  for (size_t i = 0; i < bars.size(); ++i) {
    const double prev_close = i > 0 ? bars[i - 1].close : bars[i].close;
    const double high_low = bars[i].high - bars[i].low;
    tr[i] = std::max(high_low, std::max(std::abs(bars[i].high - prev_close),
                                        std::abs(bars[i].low - prev_close)));
    sum += tr[i];
    if (i >= static_cast<size_t>(period)) sum -= tr[i - period];
    const size_t n = std::min(i + 1, static_cast<size_t>(period));
    atr[i] = sum / static_cast<double>(n);
  }
  return atr;
}

// ── Stop planning ──────────────────────────────────────────────────────────

StopPlan build_stop_plan(const StrategySignal& sig, const TradeConfig& tc,
                         const std::vector<double>& atr, double raw) {
  StopPlan pl;
  double sl_dist = 0.0, tp_dist = 0.0;

  if (sig.has_stop_loss) {
    const double d = sig.side == TradeSide::Long ? raw - sig.stop_loss : sig.stop_loss - raw;
    if (d > 0.0) sl_dist = d;
  } else if (tc.stop_type == StopType::ATR) {
    if (!atr.empty() && tc.atr_sl_multiplier > 0.0)
      sl_dist = atr[static_cast<size_t>(sig.bar_index)] * tc.atr_sl_multiplier;
  } else if (tc.stop_type == StopType::Fixed) {
    sl_dist = tc.stop_loss;
  }

  if (sig.has_take_profit) {
    const double d = sig.side == TradeSide::Long ? sig.take_profit - raw : raw - sig.take_profit;
    if (d > 0.0) tp_dist = d;
  } else if (tc.stop_type == StopType::ATR) {
    if (!atr.empty() && tc.atr_tp_multiplier > 0.0)
      tp_dist = atr[static_cast<size_t>(sig.bar_index)] * tc.atr_tp_multiplier;
  } else if (tc.stop_type == StopType::Fixed) {
    tp_dist = tc.take_profit;
  }

  double trailing = 0.0;
  if (sig.has_trailing_stop) {
    trailing = sig.trailing_stop;
  } else if (!atr.empty() && tc.atr_trailing_multiplier > 0.0) {
    trailing = atr[static_cast<size_t>(sig.bar_index)] * tc.atr_trailing_multiplier;
  } else {
    trailing = tc.trailing_stop;
  }

  const double ref_dist = sl_dist > 0.0 ? sl_dist : tp_dist;
  pl.stop_distance = sl_dist;
  pl.stop_level = sl_dist > 0.0
                      ? (sig.side == TradeSide::Long ? raw - sl_dist : raw + sl_dist)
                      : 0.0;
  pl.tp_distance = tp_dist;
  pl.tp_level = tp_dist > 0.0
                    ? (sig.side == TradeSide::Long ? raw + tp_dist : raw - tp_dist)
                    : 0.0;
  pl.trailing_distance = trailing;
  pl.activation_distance = tc.trailing_activation_pct * ref_dist;
  pl.break_even_activation = tc.break_even_activation_pct * sl_dist;

  double pt_dist = 0.0;
  if (tc.partial_close_pct > 0.0) {
    pt_dist = tc.partial_close_target_pct > 0.0
                  ? tc.partial_close_target_pct * sl_dist
                  : tp_dist;
  }
  pl.partial_target =
      pt_dist > 0.0 ? (sig.side == TradeSide::Long ? raw + pt_dist : raw - pt_dist) : 0.0;
  return pl;
}

// ── Costs ──────────────────────────────────────────────────────────────────

double apply_exit_costs(const TradeConfig& tc, TradeSide side, double raw) {
  const double dir = side == TradeSide::Long ? -1.0 : 1.0;
  return raw + dir * tc.slippage_pct * raw + dir * (tc.spread_pct / 2.0) * raw;
}

// ── Fill accounting ────────────────────────────────────────────────────────

void close_partial(Context& ctx, OpenPosition& p, double raw_fill, double pct) {
  const double closed_qty = p.quantity * pct;
  const double exit_fill = apply_exit_costs(ctx.cfg.trade, p.side, raw_fill);
  const double gross = (exit_fill - p.entry_price) * closed_qty * p.sign();
  const double commission = exit_fill * closed_qty * ctx.cfg.trade.commission_pct +
                            closed_qty * ctx.cfg.trade.commission_per_lot;
  const double net = gross - commission;
  p.slippage += std::abs(exit_fill - raw_fill) * closed_qty;
  p.realized_pnl += net;
  p.total_commission += commission;
  p.avg_exit_price =
      (p.avg_exit_price * p.closed_quantity + exit_fill * closed_qty) /
      (p.closed_quantity + closed_qty);
  p.closed_quantity += closed_qty;
  p.quantity -= closed_qty;
  p.partial_closed = true;
  ++p.partial_fill_count;
  ctx.cash += net;
}

void close_position(Context& ctx, OpenPosition& p, double raw_fill, ExitReason reason,
                    int64_t exit_bar, TimePoint exit_time) {
  const double qty = p.quantity;
  const double exit_fill = apply_exit_costs(ctx.cfg.trade, p.side, raw_fill);
  const double gross = (exit_fill - p.entry_price) * qty * p.sign();
  const double commission = exit_fill * qty * ctx.cfg.trade.commission_pct +
                            qty * ctx.cfg.trade.commission_per_lot;
  const double net = gross - commission;
  p.slippage += std::abs(exit_fill - raw_fill) * qty;
  p.realized_pnl += net;
  p.total_commission += commission;
  p.avg_exit_price =
      (p.avg_exit_price * p.closed_quantity + exit_fill * qty) /
      (p.closed_quantity + qty);
  p.closed_quantity += qty;
  p.quantity = 0.0;
  ctx.cash += net;

  TradeResult tr;
  tr.trade_id = p.id;
  tr.side = p.side;
  tr.entry_bar = p.entry_bar;
  tr.exit_bar = exit_bar;
  tr.entry_time = p.entry_time;
  tr.exit_time = exit_time;
  tr.entry_price = p.entry_price;
  tr.exit_price = exit_fill;
  tr.avg_exit_price = p.avg_exit_price;
  tr.quantity = p.entry_quantity;
  tr.gross_pnl = p.realized_pnl + p.total_commission;
  tr.net_pnl = p.realized_pnl;
  tr.net_pnl_pct = p.entry_value > 0.0 ? p.realized_pnl / p.entry_value * 100.0 : 0.0;
  tr.r_multiple = p.risked_amount > 0.0 ? p.realized_pnl / p.risked_amount : 0.0;
  tr.commission = p.total_commission;
  tr.slippage = p.slippage;
  tr.mfe = p.mfe;
  tr.mae = p.mae;
  tr.bars_held = p.entry_bar < exit_bar ? (exit_bar - p.entry_bar + 1) : 1;
  tr.exit_reason = reason;
  tr.partial_close = p.partial_fill_count > 0;
  tr.partial_fill_count = p.partial_fill_count;
  ctx.result->trades.push_back(std::move(tr));
}

void close_all(Context& ctx, double raw_fill, ExitReason reason, int64_t bar_idx,
               TimePoint ts) {
  if (ctx.positions.empty()) return;
  for (auto& p : ctx.positions) close_position(ctx, p, raw_fill, reason, bar_idx, ts);
  ctx.positions.clear();
}

// ── Access helpers ─────────────────────────────────────────────────────────

std::vector<OpenPosition>::iterator find_last_of_side(std::vector<OpenPosition>& v,
                                                      TradeSide side) {
  for (auto it = v.rbegin(); it != v.rend(); ++it)
    if (it->side == side) return (it + 1).base();
  return v.end();
}

bool trading_allowed(const Context& ctx, const OHLCV& bar) {
  if (ctx.cfg.risk.session.enabled) {
    const auto up = detail::utc_parts(bar.timestamp);
    if (!ctx.cfg.risk.session.allows(up.hour, up.weekday)) return false;
  }
  if (ctx.loss_limit_hit) return false;
  if (ctx.cfg.risk.max_open_positions > 0 &&
      ctx.positions.size() >= ctx.cfg.risk.max_open_positions)
    return false;
  if (ctx.cfg.risk.max_trades_per_day > 0 &&
      ctx.daily_trades >= ctx.cfg.risk.max_trades_per_day)
    return false;
  return true;
}

double size_quantity(const Context& ctx, const StrategySignal& sig, const StopPlan& plan) {
  const TradeConfig& tc = ctx.cfg.trade;
  if (tc.sizing == PositionSizing::FixedLot) return tc.fixed_lot;
  const double risk = sig.risk_amount > 0.0
                          ? sig.risk_amount
                          : (tc.risk_amount > 0.0
                                 ? tc.risk_amount
                                 : ctx.current_equity * tc.risk_percent / 100.0);
  if (plan.stop_distance <= 0.0) return 0.0;
  return risk > 0.0 ? risk / plan.stop_distance : 0.0;
}

// ── Signal execution ───────────────────────────────────────────────────────

void execute_signal(Context& ctx, const StrategySignal& sig, const OHLCV& bar,
                    int64_t bar_idx) {
  const TradeConfig& tc = ctx.cfg.trade;

  switch (sig.action) {
    case SignalAction::Open: {
      if (sig.side == TradeSide::Long && !tc.allow_long) { ++ctx.signals_ignored; return; }
      if (sig.side == TradeSide::Short && !tc.allow_short) { ++ctx.signals_ignored; return; }
      if (!trading_allowed(ctx, bar)) { ++ctx.signals_ignored; return; }

      const double raw = bar.open;
      const double reference = ctx.bars[static_cast<size_t>(sig.bar_index)].close;
      const StopPlan plan = build_stop_plan(sig, tc, ctx.atr, reference);
      const double qty = size_quantity(ctx, sig, plan);
      if (qty <= 0.0) { ++ctx.signals_ignored; return; }

      const double dir = sig.side == TradeSide::Long ? 1.0 : -1.0;
      const double entry_price = raw + dir * tc.slippage_pct * raw + dir * (tc.spread_pct / 2.0) * raw;
      const double entry_value = qty * raw;
      const double commission = entry_value * tc.commission_pct + qty * tc.commission_per_lot;

      OpenPosition p;
      p.id = ctx.next_id++;
      p.entry_bar = bar_idx;
      p.entry_time = bar.timestamp;
      p.side = sig.side;
      p.entry_price = entry_price;
      p.open_raw = raw;
      p.quantity = qty;
      p.entry_quantity = qty;
      p.stop_loss = plan.stop_level;
      p.take_profit = plan.tp_level;
      p.initial_stop = plan.stop_level;
      p.trailing_distance = plan.trailing_distance;
      p.activation_distance = plan.activation_distance;
      p.break_even_activation = plan.break_even_activation;
      p.partial_target = plan.partial_target;
      p.entry_commission = commission;
      p.total_commission = commission;
      p.realized_pnl = -commission;
      p.entry_value = entry_value;
      p.risked_amount = plan.stop_distance > 0.0 ? plan.stop_distance * qty : 0.0;
      p.slippage = std::abs(entry_price - raw) * qty;
      ctx.cash -= commission;
      ctx.positions.push_back(std::move(p));
      ++ctx.signals_opened;
      ++ctx.daily_trades;
      return;
    }
    case SignalAction::Close: {
      auto it = find_last_of_side(ctx.positions, sig.side);
      if (it == ctx.positions.end()) { ++ctx.signals_ignored; return; }
      close_position(ctx, *it, bar.open, ExitReason::Signal, bar_idx, bar.timestamp);
      ctx.positions.erase(it);
      return;
    }
    case SignalAction::CloseAll: {
      if (ctx.positions.empty()) { ++ctx.signals_ignored; return; }
      for (auto& p : ctx.positions)
        close_position(ctx, p, bar.open, ExitReason::Signal, bar_idx, bar.timestamp);
      ctx.positions.clear();
      return;
    }
    case SignalAction::Modify: {
      auto it = find_last_of_side(ctx.positions, sig.side);
      if (it == ctx.positions.end()) { ++ctx.signals_ignored; return; }
      if (sig.has_stop_loss) it->stop_loss = sig.stop_loss;
      if (sig.has_take_profit) it->take_profit = sig.take_profit;
      if (sig.has_trailing_stop) it->trailing_distance = sig.trailing_stop;
      return;
    }
    default:
      return;
  }
}

// ── Per-bar position management ────────────────────────────────────────────

bool manage_one(Context& ctx, OpenPosition& p, const OHLCV& bar, int64_t bar_idx) {
  const TradeConfig& tc = ctx.cfg.trade;
  p.update_mfe_mae(bar.high, bar.low);
  ++p.bars_open;

  // Price exits first; the stop takes priority over the take-profit
  // (conservative: when both are inside one candle, the stop fills).
  if (p.stop_hit(bar.high, bar.low)) {
    const double raw = p.stop_fill(bar.open);
    const ExitReason reason = p.trailing_active ? ExitReason::TrailingStop
                              : (p.break_even_moved ? ExitReason::BreakEven
                                                    : ExitReason::StopLoss);
    close_position(ctx, p, raw, reason, bar_idx, bar.timestamp);
    return true;
  }
  if (p.tp_hit(bar.high, bar.low)) {
    close_position(ctx, p, p.tp_fill(bar.open), ExitReason::TakeProfit, bar_idx,
                   bar.timestamp);
    return true;
  }

  // Partial close at the partial target.
  if (!p.partial_closed && tc.partial_close_pct > 0.0 && p.partial_target > 0.0) {
    const bool hit = p.is_long() ? bar.high >= p.partial_target : bar.low <= p.partial_target;
    if (hit) {
      const double raw = p.is_long() ? std::max(bar.open, p.partial_target)
                                     : std::min(bar.open, p.partial_target);
      close_partial(ctx, p, raw, tc.partial_close_pct);
    }
  }

  const double best = p.is_long() ? bar.high : bar.low;

  // Break-even move.
  if (!p.break_even_moved && p.break_even_activation > 0.0 &&
      p.profit_per_unit(best) >= p.break_even_activation) {
    p.move_stop_to_break_even();
  }

  // Trailing stop (ratchets only in the direction of profit).
  if (p.trailing_distance > 0.0) {
    if (!p.trailing_active &&
        (p.activation_distance <= 0.0 || p.profit_per_unit(best) >= p.activation_distance)) {
      p.trailing_active = true;
    }
    if (p.trailing_active) p.ratchet_trailing(best);
  }

  // Time stop.
  if (tc.max_bars_in_trade > 0 && p.bars_open >= tc.max_bars_in_trade) {
    close_position(ctx, p, bar.close, ExitReason::TimeStop, bar_idx, bar.timestamp);
    return true;
  }
  return false;
}

void manage_positions(Context& ctx, const OHLCV& bar, int64_t bar_idx) {
  size_t w = 0;
  for (size_t r = 0; r < ctx.positions.size(); ++r) {
    OpenPosition& p = ctx.positions[r];
    if (!manage_one(ctx, p, bar, bar_idx)) ctx.positions[w++] = std::move(p);
  }
  ctx.positions.resize(w);
}

double mark_to_market(const Context& ctx, double close) {
  double eq = ctx.cash;
  for (const auto& p : ctx.positions) eq += p.unrealized_pnl(close);
  return eq;
}

// ── Statistics ─────────────────────────────────────────────────────────────

double periods_per_year(const std::vector<OHLCV>& bars) {
  if (bars.size() < 2) return 252.0;
  std::vector<int64_t> deltas;
  deltas.reserve(bars.size() - 1);
  for (size_t i = 1; i < bars.size(); ++i) {
    deltas.push_back(std::chrono::duration_cast<std::chrono::seconds>(
                         bars[i].timestamp - bars[i - 1].timestamp)
                         .count());
  }
  std::sort(deltas.begin(), deltas.end());
  const double med = static_cast<double>(deltas[deltas.size() / 2]);
  return med > 0.0 ? (365.25 * 86400.0) / med : 252.0;
}

void compute_stats(SimulationResult& r, const std::vector<OHLCV>& bars) {
  auto& s = r.stats;
  s.total_trades = r.trades.size();

  double gross_profit = 0.0, gross_loss = 0.0, net = 0.0, sum_r = 0.0;
  size_t wins = 0, losses = 0, breakeven = 0;
  size_t cur_w = 0, cur_l = 0, max_w = 0, max_l = 0;
  for (const auto& t : r.trades) {
    net += t.net_pnl;
    sum_r += t.r_multiple;
    s.total_commission += t.commission;
    s.total_slippage += t.slippage;
    if (t.is_profitable()) {
      ++wins;
      gross_profit += t.net_pnl;
      ++cur_w;
      cur_l = 0;
      max_w = std::max(max_w, cur_w);
    } else if (t.is_loss()) {
      ++losses;
      gross_loss += -t.net_pnl;
      ++cur_l;
      cur_w = 0;
      max_l = std::max(max_l, cur_l);
    } else {
      ++breakeven;
    }
  }

  s.winning_trades = wins;
  s.losing_trades = losses;
  s.breakeven_trades = breakeven;
  s.win_rate = s.total_trades ? static_cast<double>(wins) / s.total_trades * 100.0 : 0.0;
  s.average_win = wins ? gross_profit / static_cast<double>(wins) : 0.0;
  s.average_loss = losses ? -gross_loss / static_cast<double>(losses) : 0.0;
  s.average_rr = s.average_loss != 0.0
                     ? std::abs(s.average_win / s.average_loss)
                     : (wins ? std::numeric_limits<double>::infinity() : 0.0);
  s.gross_profit = gross_profit;
  s.gross_loss = gross_loss;
  s.profit_factor = gross_loss > 0.0
                        ? gross_profit / gross_loss
                        : (gross_profit > 0.0 ? std::numeric_limits<double>::infinity() : 0.0);
  s.net_profit = net;
  s.expectancy = s.total_trades ? net / static_cast<double>(s.total_trades) : 0.0;
  s.expectancy_r = s.total_trades ? sum_r / static_cast<double>(s.total_trades) : 0.0;
  s.max_consecutive_wins = max_w;
  s.max_consecutive_losses = max_l;

  if (!r.equity_curve.empty()) {
    double peak = r.equity_curve[0];
    double max_dd = 0.0;
    double max_dd_peak = peak;
    for (double eq : r.equity_curve) {
      if (eq > peak) peak = eq;
      const double dd = peak > 0.0 ? (peak - eq) / peak : 0.0;
      if (dd > max_dd) {
        max_dd = dd;
        max_dd_peak = peak;
      }
    }
    s.max_drawdown_pct = max_dd * 100.0;
    s.max_drawdown = max_dd_peak * max_dd;
  }

  const size_t n = r.equity_curve.size();
  if (n >= 2) {
    double mean = 0.0;
    std::vector<double> rets;
    rets.reserve(n - 1);
    for (size_t i = 1; i < n; ++i) {
      const double prev = r.equity_curve[i - 1];
      const double rr = prev > 0.0 ? (r.equity_curve[i] - prev) / prev : 0.0;
      rets.push_back(rr);
      mean += rr;
    }
    mean /= static_cast<double>(n - 1);
    double var = 0.0, downside = 0.0;
    for (double rr : rets) {
      const double d = rr - mean;
      var += d * d;
      if (rr < 0.0) downside += rr * rr;
    }
    var /= static_cast<double>(n - 1);
    const double sd = std::sqrt(var);
    const double downside_dev = std::sqrt(downside / static_cast<double>(n - 1));
    const double periods = periods_per_year(bars);

    s.annualized_volatility = sd * std::sqrt(periods);
    if (sd > 0.0) s.sharpe = (mean / sd) * std::sqrt(periods);
    if (downside_dev > 0.0) {
      s.sortino = (mean / downside_dev) * std::sqrt(periods);
    } else if (mean > 0.0) {
      s.sortino = std::numeric_limits<double>::infinity();
    }

    const double initial = r.initial_equity;
    const double final = r.final_equity;
    if (initial > 0.0) s.total_return_pct = (final / initial - 1.0) * 100.0;
    if (initial > 0.0 && final > 0.0 && n > 0)
      s.annualized_return = std::pow(final / initial, periods / static_cast<double>(n)) - 1.0;
    if (s.max_drawdown_pct > 0.0)
      s.calmar = (s.annualized_return * 100.0) / s.max_drawdown_pct;
  }

  if (!r.drawdown_curve.empty()) {
    double acc = 0.0;
    for (double dd : r.drawdown_curve) acc += dd * dd;
    s.ulcer_index = std::sqrt(acc / static_cast<double>(r.drawdown_curve.size()));
  }

  if (s.max_drawdown > 0.0) s.recovery_factor = s.net_profit / s.max_drawdown;
}

// ── Calendar period returns ────────────────────────────────────────────────

std::vector<PeriodReturn> build_period_returns(const std::vector<OHLCV>& bars,
                                               const SimulationResult& r, int granularity) {
  std::vector<PeriodReturn> out;
  std::string cur;
  double period_start = r.initial_equity;
  double last_eq = r.initial_equity;
  for (size_t i = 0; i < bars.size(); ++i) {
    const auto up = detail::utc_parts(bars[i].timestamp);
    char buf[16];
    if (granularity == 1)
      std::snprintf(buf, sizeof(buf), "%04d-%02d", up.year, up.month);
    else
      std::snprintf(buf, sizeof(buf), "%04d", up.year);
    std::string lbl(buf);
    if (cur.empty()) cur = lbl;
    if (lbl != cur) {
      PeriodReturn pr;
      pr.label = cur;
      pr.start_equity = period_start;
      pr.end_equity = last_eq;
      pr.return_pct = period_start > 0.0 ? (last_eq / period_start - 1.0) * 100.0 : 0.0;
      out.push_back(std::move(pr));
      cur = lbl;
      period_start = last_eq;
    }
    last_eq = r.equity_curve[i];
  }
  if (!cur.empty()) {
    PeriodReturn pr;
    pr.label = cur;
    pr.start_equity = period_start;
    pr.end_equity = last_eq;
    pr.return_pct = period_start > 0.0 ? (last_eq / period_start - 1.0) * 100.0 : 0.0;
    out.push_back(std::move(pr));
  }
  return out;
}

} // namespace

// ── StrategyKernel ─────────────────────────────────────────────────────────

StrategyKernel::StrategyKernel(StrategyConfig config) : config_(std::move(config)) {}

void StrategyKernel::set_config(StrategyConfig config) { config_ = std::move(config); }

const StrategyConfig& StrategyKernel::config() const { return config_; }

Result<SimulationResult> StrategyKernel::run(const std::vector<OHLCV>& bars,
                                             const std::vector<StrategySignal>& signals,
                                             bool compute_hash) {
  if (bars.empty())
    return Error(ErrorCode::InsufficientData, "strategy kernel requires at least one bar");
  for (size_t i = 0; i < bars.size(); ++i) {
    if (!bars[i].is_valid())
      return Error(ErrorCode::InvalidArgument,
                   "invalid OHLC bar at index " + std::to_string(i));
    if (i > 0 && bars[i].timestamp < bars[i - 1].timestamp)
      return Error(ErrorCode::InvalidArgument, "bar timestamps must be non-decreasing");
  }
  for (const auto& s : signals) {
    if (s.bar_index < 0 || s.bar_index >= static_cast<int64_t>(bars.size()))
      return Error(ErrorCode::OutOfBounds, "signal bar_index out of range");
  }

  const TradeConfig& tc = config_.trade;

  // Sort the signal stream by bar index (stable: equal bar indices keep input
  // order) so execution is deterministic regardless of the caller's ordering.
  std::vector<const StrategySignal*> ordered;
  ordered.reserve(signals.size());
  for (const auto& s : signals) ordered.push_back(&s);
  std::stable_sort(ordered.begin(), ordered.end(),
                   [](const StrategySignal* a, const StrategySignal* b) {
                     return a->bar_index < b->bar_index;
                   });

  const bool need_atr = tc.stop_type == StopType::ATR || tc.atr_sl_multiplier > 0.0 ||
                        tc.atr_tp_multiplier > 0.0 || tc.atr_trailing_multiplier > 0.0;
  std::vector<double> atr;
  if (need_atr) atr = compute_atr(bars, tc.atr_period);

  SimulationResult result;
  result.initial_equity = config_.risk.initial_equity;
  result.equity_curve.reserve(bars.size());
  result.drawdown_curve.reserve(bars.size());
  result.trades.reserve(std::min(signals.size(), static_cast<size_t>(1u << 18)));

  Context ctx{bars, config_, atr};
  ctx.result = &result;
  ctx.cash = config_.risk.initial_equity;
  ctx.current_equity = config_.risk.initial_equity;
  ctx.positions.reserve(config_.risk.max_open_positions > 0
                            ? config_.risk.max_open_positions
                            : 1024);
  ctx.pending.reserve(ordered.size());

  const RiskConfig& rc = config_.risk;
  const bool need_daily = rc.daily_loss_limit_pct > 0.0 || rc.max_trades_per_day > 0.0;
  const bool need_session = rc.session.enabled || rc.close_on_session_end;

  double peak_eq = config_.risk.initial_equity;
  size_t si = 0;

  for (size_t i = 0; i < bars.size(); ++i) {
    const OHLCV& bar = bars[i];

    if (need_daily || need_session) {
      const auto up = detail::utc_parts(bar.timestamp);
      if (need_daily && up.day_key != ctx.last_day_key) {
        ctx.last_day_key = up.day_key;
        ctx.daily_start_equity = ctx.current_equity;
        ctx.daily_trades = 0;
        ctx.loss_limit_hit = false;
      }
      if (rc.close_on_session_end && rc.session.enabled) {
        const bool in = rc.session.allows(up.hour, up.weekday);
        if (ctx.prev_session_known && ctx.prev_in_session && !in)
          close_all(ctx, bar.open, ExitReason::SessionClose, static_cast<int64_t>(i),
                    bar.timestamp);
        ctx.prev_in_session = in;
        ctx.prev_session_known = true;
      }
    }

    // Execute signals queued by the previous bar at this bar's open.
    for (const StrategySignal* sig : ctx.pending) execute_signal(ctx, *sig, bar, static_cast<int64_t>(i));
    ctx.pending.clear();

    // Manage open positions through this bar.
    manage_positions(ctx, bar, static_cast<int64_t>(i));

    // Equity / drawdown at the close.
    double eq = mark_to_market(ctx, bar.close);

    // Daily loss-limit circuit breaker (at the close).
    if (rc.daily_loss_limit_pct > 0.0 && !ctx.loss_limit_hit &&
        eq <= ctx.daily_start_equity * (1.0 - rc.daily_loss_limit_pct / 100.0)) {
      ctx.loss_limit_hit = true;
      close_all(ctx, bar.close, ExitReason::DailyLossLimit, static_cast<int64_t>(i),
                bar.timestamp);
      eq = ctx.cash;
    }

    ctx.current_equity = eq;
    result.equity_curve.push_back(eq);
    if (eq > peak_eq) peak_eq = eq;
    const double dd_pct = peak_eq > 0.0 ? (peak_eq - eq) / peak_eq * 100.0 : 0.0;
    result.drawdown_curve.push_back(dd_pct);

    // Queue this bar's signals (filled at the open of bar i+1).
    while (si < ordered.size() && ordered[si]->bar_index == static_cast<int64_t>(i)) {
      const StrategySignal* sig = ordered[si];
      if (ctx.loss_limit_hit && sig->action == SignalAction::Open) {
        ++ctx.signals_ignored;
      } else {
        ctx.pending.push_back(sig);
      }
      ++si;
      ++result.signals_processed;
    }
  }

  // Liquidate anything still open at the final close.
  if (!ctx.positions.empty())
    close_all(ctx, bars.back().close, ExitReason::EndOfData,
              static_cast<int64_t>(bars.size()) - 1, bars.back().timestamp);

  result.bars_processed = bars.size();
  result.signals_opened = ctx.signals_opened;
  result.signals_ignored = ctx.signals_ignored;
  result.final_equity = ctx.cash;

  compute_stats(result, bars);
  result.monthly_returns = build_period_returns(bars, result, 1);
  result.yearly_returns = build_period_returns(bars, result, 2);

  if (compute_hash) {
    result.input_hash = compute_input_hash(bars, signals, config_);
    result.result_hash = result.compute_result_hash();
  }
  return Result<SimulationResult>::ok(std::move(result));
}

// ── Input hash ─────────────────────────────────────────────────────────────

std::string compute_input_hash(const std::vector<OHLCV>& bars,
                               const std::vector<StrategySignal>& signals,
                               const StrategyConfig& config) {
  using detail::canonical_bool;
  using detail::canonical_double;
  using detail::canonical_int;
  using detail::canonical_object;
  using detail::canonical_str;
  using detail::iso8601;
  using detail::sha256_hex;

  std::string bars_json = "[";
  for (size_t i = 0; i < bars.size(); ++i) {
    if (i) bars_json += ",";
    const auto& b = bars[i];
    bars_json += canonical_object({
        {"t", canonical_str(iso8601(b.timestamp))},
        {"o", canonical_double(b.open)},
        {"h", canonical_double(b.high)},
        {"l", canonical_double(b.low)},
        {"c", canonical_double(b.close)},
        {"v", canonical_double(b.volume)},
    });
  }
  bars_json += "]";

  std::string sig_json = "[";
  std::vector<const StrategySignal*> sig_order;
  sig_order.reserve(signals.size());
  for (const auto& s : signals) sig_order.push_back(&s);
  std::stable_sort(sig_order.begin(), sig_order.end(),
                   [](const StrategySignal* a, const StrategySignal* b) {
                     return a->bar_index < b->bar_index;
                   });
  for (size_t i = 0; i < sig_order.size(); ++i) {
    if (i) sig_json += ",";
    const auto& s = *sig_order[i];
    sig_json += canonical_object({
        {"bar_index", canonical_int(s.bar_index)},
        {"action", canonical_str(action_name(s.action))},
        {"side", canonical_str(side_name(s.side))},
        {"quantity", canonical_double(s.quantity)},
        {"stop_loss", canonical_double(s.stop_loss)},
        {"take_profit", canonical_double(s.take_profit)},
        {"trailing_stop", canonical_double(s.trailing_stop)},
        {"has_stop_loss", canonical_bool(s.has_stop_loss)},
        {"has_take_profit", canonical_bool(s.has_take_profit)},
        {"has_trailing_stop", canonical_bool(s.has_trailing_stop)},
        {"risk_amount", canonical_double(s.risk_amount)},
    });
  }
  sig_json += "]";

  const auto& t = config.trade;
  const auto& r = config.risk;
  const auto& sess = r.session;
  const char* sizing_name =
      t.sizing == PositionSizing::FixedLot ? "FixedLot" : "RiskPercent";
  const char* stop_name = t.stop_type == StopType::ATR
                              ? "ATR"
                              : (t.stop_type == StopType::Fixed ? "Fixed" : "None");

  const std::string cfg_json = canonical_object({
      {"trade", canonical_object({
          {"sizing", canonical_str(sizing_name)},
          {"fixed_lot", canonical_double(t.fixed_lot)},
          {"risk_percent", canonical_double(t.risk_percent)},
          {"risk_amount", canonical_double(t.risk_amount)},
          {"default_quantity", canonical_double(t.default_quantity)},
          {"commission_pct", canonical_double(t.commission_pct)},
          {"commission_per_lot", canonical_double(t.commission_per_lot)},
          {"spread_pct", canonical_double(t.spread_pct)},
          {"slippage_pct", canonical_double(t.slippage_pct)},
          {"stop_type", canonical_str(stop_name)},
          {"stop_loss", canonical_double(t.stop_loss)},
          {"take_profit", canonical_double(t.take_profit)},
          {"atr_period", canonical_int(t.atr_period)},
          {"atr_sl_multiplier", canonical_double(t.atr_sl_multiplier)},
          {"atr_tp_multiplier", canonical_double(t.atr_tp_multiplier)},
          {"trailing_stop", canonical_double(t.trailing_stop)},
          {"atr_trailing_multiplier", canonical_double(t.atr_trailing_multiplier)},
          {"trailing_activation_pct", canonical_double(t.trailing_activation_pct)},
          {"break_even_activation_pct", canonical_double(t.break_even_activation_pct)},
          {"partial_close_pct", canonical_double(t.partial_close_pct)},
          {"partial_close_target_pct", canonical_double(t.partial_close_target_pct)},
          {"max_bars_in_trade", canonical_int(t.max_bars_in_trade)},
          {"allow_long", canonical_bool(t.allow_long)},
          {"allow_short", canonical_bool(t.allow_short)},
      })},
      {"risk", canonical_object({
          {"initial_equity", canonical_double(r.initial_equity)},
          {"daily_loss_limit_pct", canonical_double(r.daily_loss_limit_pct)},
          {"max_open_positions", canonical_int(static_cast<int64_t>(r.max_open_positions))},
          {"max_trades_per_day", canonical_int(static_cast<int64_t>(r.max_trades_per_day))},
          {"close_on_session_end", canonical_bool(r.close_on_session_end)},
          {"session", canonical_object({
              {"enabled", canonical_bool(sess.enabled)},
              {"utc_start_hour", canonical_int(sess.utc_start_hour)},
              {"utc_end_hour", canonical_int(sess.utc_end_hour)},
              {"allow_saturday", canonical_bool(sess.allow_saturday)},
              {"allow_sunday", canonical_bool(sess.allow_sunday)},
          })},
      })},
  });

  return sha256_hex(canonical_object({
      {"bars", bars_json},
      {"config", cfg_json},
      {"signals", sig_json},
  }));
}

// ── Result hash ────────────────────────────────────────────────────────────

std::string SimulationResult::compute_result_hash() const {
  using detail::canonical_bool;
  using detail::canonical_double;
  using detail::canonical_double_array;
  using detail::canonical_int;
  using detail::canonical_object;
  using detail::canonical_str;
  using detail::iso8601;
  using detail::sha256_hex;

  std::string trades_json = "[";
  for (size_t i = 0; i < trades.size(); ++i) {
    if (i) trades_json += ",";
    const auto& t = trades[i];
    trades_json += canonical_object({
        {"id", canonical_int(t.trade_id)},
        {"side", canonical_str(side_name(t.side))},
        {"entry_bar", canonical_int(t.entry_bar)},
        {"exit_bar", canonical_int(t.exit_bar)},
        {"entry_time", canonical_str(iso8601(t.entry_time))},
        {"exit_time", canonical_str(iso8601(t.exit_time))},
        {"entry_price", canonical_double(t.entry_price)},
        {"exit_price", canonical_double(t.exit_price)},
        {"avg_exit_price", canonical_double(t.avg_exit_price)},
        {"quantity", canonical_double(t.quantity)},
        {"gross_pnl", canonical_double(t.gross_pnl)},
        {"net_pnl", canonical_double(t.net_pnl)},
        {"net_pnl_pct", canonical_double(t.net_pnl_pct)},
        {"r_multiple", canonical_double(t.r_multiple)},
        {"commission", canonical_double(t.commission)},
        {"slippage", canonical_double(t.slippage)},
        {"mfe", canonical_double(t.mfe)},
        {"mae", canonical_double(t.mae)},
        {"bars_held", canonical_int(t.bars_held)},
        {"exit_reason", canonical_str(exit_reason_name(t.exit_reason))},
        {"partial_close", canonical_bool(t.partial_close)},
        {"partial_fill_count", canonical_int(t.partial_fill_count)},
    });
  }
  trades_json += "]";

  auto period_to_json = [](const PeriodReturn& pr) {
    return canonical_object({
        {"label", canonical_str(pr.label)},
        {"return_pct", canonical_double(pr.return_pct)},
        {"start_equity", canonical_double(pr.start_equity)},
        {"end_equity", canonical_double(pr.end_equity)},
    });
  };
  std::string monthly_json = "[";
  for (size_t i = 0; i < monthly_returns.size(); ++i) {
    if (i) monthly_json += ",";
    monthly_json += period_to_json(monthly_returns[i]);
  }
  monthly_json += "]";
  std::string yearly_json = "[";
  for (size_t i = 0; i < yearly_returns.size(); ++i) {
    if (i) yearly_json += ",";
    yearly_json += period_to_json(yearly_returns[i]);
  }
  yearly_json += "]";

  const auto& s = stats;
  return sha256_hex(canonical_object({
      {"input_hash", canonical_str(input_hash)},
      {"initial_equity", canonical_double(initial_equity)},
      {"final_equity", canonical_double(final_equity)},
      {"bars_processed", canonical_int(static_cast<int64_t>(bars_processed))},
      {"signals_processed", canonical_int(static_cast<int64_t>(signals_processed))},
      {"signals_opened", canonical_int(static_cast<int64_t>(signals_opened))},
      {"signals_ignored", canonical_int(static_cast<int64_t>(signals_ignored))},
      {"equity_curve", canonical_double_array(equity_curve)},
      {"trades", trades_json},
      {"monthly_returns", monthly_json},
      {"yearly_returns", yearly_json},
      {"stats", canonical_object({
          {"total_trades", canonical_int(static_cast<int64_t>(s.total_trades))},
          {"winning_trades", canonical_int(static_cast<int64_t>(s.winning_trades))},
          {"losing_trades", canonical_int(static_cast<int64_t>(s.losing_trades))},
          {"breakeven_trades", canonical_int(static_cast<int64_t>(s.breakeven_trades))},
          {"win_rate", canonical_double(s.win_rate)},
          {"average_win", canonical_double(s.average_win)},
          {"average_loss", canonical_double(s.average_loss)},
          {"average_rr", canonical_double(s.average_rr)},
          {"profit_factor", canonical_double(s.profit_factor)},
          {"expectancy", canonical_double(s.expectancy)},
          {"expectancy_r", canonical_double(s.expectancy_r)},
          {"gross_profit", canonical_double(s.gross_profit)},
          {"gross_loss", canonical_double(s.gross_loss)},
          {"net_profit", canonical_double(s.net_profit)},
          {"max_drawdown", canonical_double(s.max_drawdown)},
          {"max_drawdown_pct", canonical_double(s.max_drawdown_pct)},
          {"max_consecutive_losses", canonical_int(static_cast<int64_t>(s.max_consecutive_losses))},
          {"max_consecutive_wins", canonical_int(static_cast<int64_t>(s.max_consecutive_wins))},
          {"recovery_factor", canonical_double(s.recovery_factor)},
          {"sharpe", canonical_double(s.sharpe)},
          {"sortino", canonical_double(s.sortino)},
          {"calmar", canonical_double(s.calmar)},
          {"ulcer_index", canonical_double(s.ulcer_index)},
          {"total_commission", canonical_double(s.total_commission)},
          {"total_slippage", canonical_double(s.total_slippage)},
          {"total_return_pct", canonical_double(s.total_return_pct)},
          {"annualized_return", canonical_double(s.annualized_return)},
          {"annualized_volatility", canonical_double(s.annualized_volatility)},
      })},
  }));
}

} // namespace strategy
} // namespace quant
