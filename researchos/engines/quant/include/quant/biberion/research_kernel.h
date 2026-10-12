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

}  // namespace quant::biberion
