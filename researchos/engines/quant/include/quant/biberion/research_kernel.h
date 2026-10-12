#pragma once

#include <cstddef>
#include <deque>
#include <string>
#include <vector>

namespace quant::biberion {

class VolumeSurge {
public:
    explicit VolumeSurge(std::size_t window = 50, double sigma_multiplier = 2.0);
    bool observe(double volume);
    double threshold() const;
    std::size_t samples() const noexcept;

private:
    std::size_t window_;
    double k_;
    std::deque<double> values_;
    double last_threshold_;
};

struct Signal {
    int direction{0};  // +1 long, -1 short, 0 no signal
    bool approved{false};
    std::string reason{"insufficient_history"};
};

Signal evaluate_cross(const std::vector<double>& closes,
                      const std::vector<double>& benchmark_closes,
                      std::size_t fast_window,
                      std::size_t slow_window,
                      bool volume_surge,
                      bool sideline_lockdown);

struct BasketLimits {
    double equity{0.0};
    std::size_t max_assets{10};
    double max_basket_fraction{0.10};
    double max_asset_fraction{0.01};
    double max_asset_risk_fraction{0.001};
    double max_basket_risk_fraction{0.005};
};

struct BasketProposal {
    std::string symbol;
    double entry{0.0};
    double stop{0.0};
    double requested_notional{0.0};
};

struct BasketDecision {
    bool approved{false};
    double total_notional{0.0};
    double planned_loss{0.0};
    std::string reason{"rejected"};
};

// Cash-only long proposals; no broker calls, margin, or order dispatch.
BasketDecision approve_cash_basket(const BasketLimits& limits,
                                   const std::vector<BasketProposal>& proposals);

/*
 * Three-state probabilistic decision model.
 * Feature order (standardized with frozen training-set statistics):
 * price_return_z, volume_z, latency_z, ofi_z, vxy_z, dxy_return_z.
 * weights are row-major [bearish(6), neutral(6), bullish(6)].
 * This kernel evaluates supplied parameters; it does not train them.
 */
struct StateModel {
    std::vector<double> weights;
    std::vector<double> bias;
    double threshold{0.75};
};

struct SafetyObservation {
    double latency_ms{0.0};
    double vxy_level{0.0};
    double dxy_abs_change_pct{0.0};
    bool dxy_fresh{false};
};

struct SafetyLimits {
    double max_latency_ms{250.0};
    double max_vxy_level{30.0};
    double max_abs_dxy_change_pct{1.0};
};

struct StateDecision {
    double p_bearish{0.0};
    double p_neutral{1.0};
    double p_bullish{0.0};
    int state{0};  // -1 bearish, 0 neutral/sideline, +1 bullish
    bool safety_passed{false};
    std::string reason{"invalid_input"};
};

StateDecision evaluate_market_state(const std::vector<double>& standardized_features,
                                    const SafetyObservation& observation,
                                    const StateModel& model,
                                    const SafetyLimits& limits);

}  // namespace quant::biberion
