#ifndef QUANT_STRATEGY_STRATEGY_CONFIG_H
#define QUANT_STRATEGY_STRATEGY_CONFIG_H

#include <cstdint>

#include <cstddef>
namespace quant {
namespace strategy {

enum class PositionSizing : uint8_t {
  FixedLot = 0,  // fixed quantity per trade
  RiskPercent,   // quantity derived from risk / stop distance
};

enum class StopType : uint8_t {
  None = 0,  // no SL / TP
  Fixed,     // SL / TP as absolute price distances
  ATR,       // SL / TP as ATR multiples
};

// Optional UTC session filter. When enabled, new positions may only be opened
// on bars whose UTC hour lies within [utc_start_hour, utc_end_hour] on an
// allowed weekday.
struct SessionFilter {
  bool enabled{false};
  int utc_start_hour{0};   // inclusive
  int utc_end_hour{23};    // inclusive; end < start wraps past midnight
  bool allow_saturday{true};
  bool allow_sunday{true};

  // `utc_dow` follows tm_wday: 0 = Sunday .. 6 = Saturday.
  bool allows_weekday(int utc_dow) const {
    if (utc_dow == 0) return allow_sunday;
    if (utc_dow == 6) return allow_saturday;
    return true;
  }

  bool allows_hour(int utc_hour) const {
    if (!enabled) return true;
    if (utc_start_hour <= utc_end_hour)
      return utc_hour >= utc_start_hour && utc_hour <= utc_end_hour;
    // wrap past midnight
    return utc_hour >= utc_start_hour || utc_hour <= utc_end_hour;
  }

  bool allows(int utc_hour, int utc_dow) const {
    return allows_hour(utc_hour) && allows_weekday(utc_dow);
  }
};

// Order-level configuration (costs, stops, sizing).
struct TradeConfig {
  PositionSizing sizing{PositionSizing::RiskPercent};
  double fixed_lot{0.0};        // used when sizing == FixedLot
  double risk_percent{1.0};     // % of equity risked per trade (RiskPercent)
  double risk_amount{0.0};      // fixed currency risk override; 0 -> risk_percent
  double default_quantity{1.0}; // quantity when risk-based sizing has no stop distance

  double commission_pct{0.001};   // fraction of notional per fill
  double commission_per_lot{0.0}; // flat per unit of quantity per fill
  double spread_pct{0.0001};      // round-trip half-spread fraction per fill
  double slippage_pct{0.0005};    // fraction of price per fill

  StopType stop_type{StopType::Fixed};
  double stop_loss{0.0};        // absolute price distance from entry (Fixed); 0 -> none
  double take_profit{0.0};      // absolute price distance from entry (Fixed); 0 -> none
  int atr_period{14};
  double atr_sl_multiplier{0.0}; // SL distance = multiplier * ATR
  double atr_tp_multiplier{0.0}; // TP distance = multiplier * ATR

  double trailing_stop{0.0};        // absolute price distance; 0 -> none
  double atr_trailing_multiplier{0.0};
  double trailing_activation_pct{0.0};   // profit >= pct * stop_distance arms trailing
  double break_even_activation_pct{0.0}; // profit >= pct * stop_distance moves stop to entry
  double partial_close_pct{0.0};         // fraction closed at the partial target; 0 -> off
  double partial_close_target_pct{0.0};  // partial target as multiple of stop distance; 0 -> use TP

  int max_bars_in_trade{0}; // time stop in bars; 0 -> none

  bool allow_long{true};
  bool allow_short{true};
};

// Portfolio-level risk configuration.
struct RiskConfig {
  double initial_equity{100'000.0};
  double daily_loss_limit_pct{0.0}; // % of start-of-day equity; 0 -> no limit
  size_t max_open_positions{0};     // 0 -> unlimited
  size_t max_trades_per_day{0};     // 0 -> unlimited
  SessionFilter session;
  bool close_on_session_end{false}; // force-close all positions when the session ends
};

struct StrategyConfig {
  TradeConfig trade;
  RiskConfig risk;
};

} // namespace strategy
} // namespace quant
#endif
