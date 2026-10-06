#ifndef QROS_LOW_LATENCY_TURING_FILTER_H
#define QROS_LOW_LATENCY_TURING_FILTER_H

#include <cstddef>
#include <cstdint>

namespace quant::low_latency {

enum class TuringFilterDecision : std::uint8_t {
  Drop = 0,
  Continue = 1,
  Accept = 2,
  Reject = 3,
};

enum TuringConstraint : std::uint8_t {
  ConstraintFinite = 1u << 0,
  ConstraintSpread = 1u << 1,
  ConstraintDepth = 1u << 2,
  ConstraintTradeVolume = 1u << 3,
  ConstraintTimestamp = 1u << 4,
  ConstraintDirectionalAnchor = 1u << 5,
  ConstraintPersistence = 1u << 6,
};

struct TuringFilterTick final {
  std::int64_t timestamp_ns{0};
  double bid{0.0};
  double ask{0.0};
  double bid_volume{0.0};
  double ask_volume{0.0};
  double trade_volume{0.0};
};

struct TuringFilterConfig final {
  double max_spread{0.0};
  double min_total_depth{0.0};
  double min_trade_volume{0.0};
  double min_abs_imbalance{0.0};
  std::uint32_t min_persistence{1};
  std::uint32_t max_samples{64};

  // P(E|H) and P(E|not H) for the mandatory directional anchor event.
  double event_probability_h{0.80};
  double event_probability_not_h{0.20};

  // SPRT boundaries in decibans. Prefer thresholds_from_error_rates().
  double lower_deciban{-10.0};
  double upper_deciban{10.0};
};

struct TuringFilterState final {
  double log_odds_deciban{0.0};
  std::uint32_t samples{0};
  std::uint32_t persistence{0};
  std::uint8_t constraint_mask{0};
  TuringFilterDecision last_decision{TuringFilterDecision::Continue};
  bool has_previous{false};
  std::int64_t last_timestamp_ns{0};
  double last_mid{0.0};
  double last_directional_imbalance{0.0};
};

struct TuringSprtThresholds final {
  double lower_deciban{0.0};
  double upper_deciban{0.0};
};

class TuringFilterEngine final {
public:
  explicit TuringFilterEngine(
      const TuringFilterConfig& config,
      bool bullish_hypothesis = true) noexcept;

  TuringFilterDecision process(const TuringFilterTick& tick) noexcept;

  std::size_t process_batch(const TuringFilterTick* ticks,
                            std::size_t count,
                            std::uint8_t* decisions) noexcept;

  void reset() noexcept;

  [[nodiscard]] const TuringFilterState& state() const noexcept {
    return state_;
  }

  [[nodiscard]] const TuringFilterConfig& config() const noexcept {
    return config_;
  }

  [[nodiscard]] bool bullish_hypothesis() const noexcept {
    return bullish_hypothesis_;
  }

  static TuringSprtThresholds thresholds_from_error_rates(
      double alpha, double beta) noexcept;

  static double evidence_deciban(double p_event_h,
                                 double p_event_not_h) noexcept;

private:
  [[nodiscard]] std::uint8_t structural_constraints(
      const TuringFilterTick& tick) const noexcept;

  [[nodiscard]] bool directional_anchor(
      const TuringFilterTick& tick,
      double& directional_imbalance) const noexcept;

  [[nodiscard]] bool persistence_anchor(
      double directional_imbalance) noexcept;

  TuringFilterConfig config_;
  TuringFilterState state_{};
  bool bullish_hypothesis_{true};
};

}  // namespace quant::low_latency

#endif  // QROS_LOW_LATENCY_TURING_FILTER_H
