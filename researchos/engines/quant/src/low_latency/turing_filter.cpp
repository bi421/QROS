#include "quant/low_latency/turing_filter.h"

#include <cmath>
#include <limits>

namespace quant::low_latency {
namespace {

constexpr std::uint8_t kStructuralMask =
    ConstraintFinite | ConstraintSpread | ConstraintDepth |
    ConstraintTradeVolume | ConstraintTimestamp;

constexpr double kLn10 = 2.302585092994045684017991454684364;

bool probability_valid(double p) noexcept {
  return std::isfinite(p) && p > 0.0 && p < 1.0;
}

bool config_valid(const TuringFilterConfig& c) noexcept {
  return std::isfinite(c.max_spread) && c.max_spread >= 0.0 &&
         std::isfinite(c.min_total_depth) && c.min_total_depth >= 0.0 &&
         std::isfinite(c.min_trade_volume) && c.min_trade_volume >= 0.0 &&
         std::isfinite(c.min_abs_imbalance) &&
         c.min_abs_imbalance >= 0.0 && c.min_abs_imbalance < 1.0 &&
         c.min_persistence > 0 && c.max_samples > 0 &&
         probability_valid(c.event_probability_h) &&
         probability_valid(c.event_probability_not_h) &&
         probability_valid(c.contradiction_probability_h) &&
         probability_valid(c.contradiction_probability_not_h) &&
         std::isfinite(c.lower_deciban) &&
         std::isfinite(c.upper_deciban) &&
         c.lower_deciban < c.upper_deciban;
}

}  // namespace

TuringFilterEngine::TuringFilterEngine(
    const TuringFilterConfig& config,
    bool bullish_hypothesis) noexcept
    : config_(config), bullish_hypothesis_(bullish_hypothesis) {}

double TuringFilterEngine::evidence_deciban(
    double p_event_h, double p_event_not_h) noexcept {
  if (!probability_valid(p_event_h) ||
      !probability_valid(p_event_not_h)) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  return (10.0 / kLn10) *
         (std::log(p_event_h) - std::log(p_event_not_h));
}

TuringSprtThresholds TuringFilterEngine::thresholds_from_error_rates(
    double alpha, double beta) noexcept {
  if (!std::isfinite(alpha) || !std::isfinite(beta) ||
      !(alpha > 0.0 && alpha < 1.0) ||
      !(beta > 0.0 && beta < 1.0)) {
    return {std::numeric_limits<double>::quiet_NaN(),
            std::numeric_limits<double>::quiet_NaN()};
  }

  const double upper_lr = (1.0 - beta) / alpha;
  const double lower_lr = beta / (1.0 - alpha);
  return {
      (10.0 / kLn10) * std::log(lower_lr),
      (10.0 / kLn10) * std::log(upper_lr),
  };
}

std::uint8_t TuringFilterEngine::structural_constraints(
    const TuringFilterTick& tick) const noexcept {
  std::uint8_t mask = 0;

  if (std::isfinite(static_cast<double>(tick.timestamp_ns)) &&
      std::isfinite(tick.bid) && std::isfinite(tick.ask) &&
      std::isfinite(tick.bid_volume) && std::isfinite(tick.ask_volume) &&
      std::isfinite(tick.trade_volume)) {
    mask |= ConstraintFinite;
  } else {
    return mask;
  }

  const double spread = tick.ask - tick.bid;
  if (tick.bid > 0.0 && tick.ask > 0.0 &&
      spread >= 0.0 && spread <= config_.max_spread) {
    mask |= ConstraintSpread;
  }

  const double total_depth = tick.bid_volume + tick.ask_volume;
  if (tick.bid_volume >= 0.0 && tick.ask_volume >= 0.0 &&
      total_depth >= config_.min_total_depth) {
    mask |= ConstraintDepth;
  }

  if (tick.trade_volume >= config_.min_trade_volume) {
    mask |= ConstraintTradeVolume;
  }

  if (!state_.has_previous || tick.timestamp_ns > state_.last_timestamp_ns) {
    mask |= ConstraintTimestamp;
  }

  return mask;
}

bool TuringFilterEngine::directional_anchor(
    const TuringFilterTick& tick,
    double& directional_imbalance) const noexcept {
  const double total = tick.bid_volume + tick.ask_volume;
  if (!(total > 0.0) || !std::isfinite(total)) return false;

  const double imbalance =
      (tick.bid_volume - tick.ask_volume) / total;
  directional_imbalance =
      bullish_hypothesis_ ? imbalance : -imbalance;

  return std::isfinite(directional_imbalance) &&
         directional_imbalance >= config_.min_abs_imbalance;
}

bool TuringFilterEngine::persistence_anchor(
    double directional_imbalance) noexcept {
  if (!state_.has_previous) {
    state_.persistence = 1;
    return state_.persistence >= config_.min_persistence;
  }

  // The anchor is broken by a sign flip or by falling below the configured
  // directional threshold. Equal-direction observations extend persistence.
  if (directional_imbalance >= config_.min_abs_imbalance &&
      state_.last_directional_imbalance >= config_.min_abs_imbalance) {
    if (state_.persistence < config_.min_persistence) {
      ++state_.persistence;
    }
  } else {
    state_.persistence = 1;
  }

  return state_.persistence >= config_.min_persistence;
}

TuringFilterDecision TuringFilterEngine::process(
    const TuringFilterTick& tick) noexcept {
  if (state_.last_decision == TuringFilterDecision::Accept ||
      state_.last_decision == TuringFilterDecision::Reject) {
    reset();
  }

  if (!config_valid(config_)) {
    reset();
    state_.constraint_mask = 0;
    state_.last_decision = TuringFilterDecision::Reject;
    return TuringFilterDecision::Reject;
  }

  const std::uint8_t structural = structural_constraints(tick);
  state_.constraint_mask = structural;

  if ((structural & kStructuralMask) != kStructuralMask) {
    state_.samples = 0;
    state_.persistence = 0;
    state_.log_odds_deciban = 0.0;
    state_.has_previous = false;
    state_.last_decision = TuringFilterDecision::Drop;
    return TuringFilterDecision::Drop;
  }

  double directional_imbalance = 0.0;
  if (!directional_anchor(tick, directional_imbalance)) {
    state_.samples = 0;
    state_.persistence = 0;
    state_.log_odds_deciban = 0.0;
    state_.has_previous = false;
    state_.constraint_mask &= static_cast<std::uint8_t>(
        ~ConstraintDirectionalAnchor);
    state_.last_decision = TuringFilterDecision::Drop;
    return TuringFilterDecision::Drop;
  }
  state_.constraint_mask |= ConstraintDirectionalAnchor;

  if (!persistence_anchor(directional_imbalance)) {
    state_.samples = 0;
    state_.log_odds_deciban = 0.0;
    state_.constraint_mask &= static_cast<std::uint8_t>(
        ~ConstraintPersistence);
    state_.last_timestamp_ns = tick.timestamp_ns;
    state_.last_mid = (tick.bid + tick.ask) * 0.5;
    state_.last_directional_imbalance = directional_imbalance;
    state_.has_previous = true;
    state_.last_decision = TuringFilterDecision::Drop;
    return TuringFilterDecision::Drop;
  }
  state_.constraint_mask |= ConstraintPersistence;

  if (state_.samples >= config_.max_samples) {
    state_.samples = 0;
    state_.persistence = 0;
    state_.log_odds_deciban = 0.0;
    state_.last_decision = TuringFilterDecision::Reject;
    return TuringFilterDecision::Reject;
  }

  const bool confirming =
      !state_.has_previous ||
      directional_imbalance >= state_.last_directional_imbalance;
  const double evidence = confirming
      ? evidence_deciban(config_.event_probability_h,
                         config_.event_probability_not_h)
      : evidence_deciban(config_.contradiction_probability_h,
                         config_.contradiction_probability_not_h);
  if (!std::isfinite(evidence)) {
    state_.samples = 0;
    state_.persistence = 0;
    state_.log_odds_deciban = 0.0;
    state_.last_decision = TuringFilterDecision::Reject;
    return TuringFilterDecision::Reject;
  }

  const double next_log_odds = state_.log_odds_deciban + evidence;
  if (!std::isfinite(next_log_odds)) {
    state_.samples = 0;
    state_.persistence = 0;
    state_.log_odds_deciban = 0.0;
    state_.last_decision = TuringFilterDecision::Reject;
    return TuringFilterDecision::Reject;
  }

  state_.log_odds_deciban = next_log_odds;
  ++state_.samples;
  state_.last_timestamp_ns = tick.timestamp_ns;
  state_.last_mid = (tick.bid + tick.ask) * 0.5;
  state_.last_directional_imbalance = directional_imbalance;
  state_.has_previous = true;

  if (state_.log_odds_deciban >= config_.upper_deciban) {
    state_.last_decision = TuringFilterDecision::Accept;
    return TuringFilterDecision::Accept;
  }
  if (state_.log_odds_deciban <= config_.lower_deciban) {
    state_.last_decision = TuringFilterDecision::Reject;
    return TuringFilterDecision::Reject;
  }
  state_.last_decision = TuringFilterDecision::Continue;
  return TuringFilterDecision::Continue;
}

std::size_t TuringFilterEngine::process_batch(
    const TuringFilterTick* ticks,
    std::size_t count,
    std::uint8_t* decisions) noexcept {
  if (count == 0) return 0;
  if (ticks == nullptr || decisions == nullptr) return 0;

  for (std::size_t i = 0; i < count; ++i) {
    decisions[i] =
        static_cast<std::uint8_t>(process(ticks[i]));
  }
  return count;
}

void TuringFilterEngine::reset() noexcept {
  state_ = TuringFilterState{};
}

}  // namespace quant::low_latency
