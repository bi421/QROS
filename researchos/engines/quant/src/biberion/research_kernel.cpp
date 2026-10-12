#include "quant/biberion/research_kernel.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <unordered_set>

namespace quant::biberion {
namespace {
bool finite_positive(double x) { return std::isfinite(x) && x > 0.0; }

double mean_tail(const std::vector<double>& values, std::size_t end,
                 std::size_t window) {
    double sum = 0.0;
    for (std::size_t i = end - window; i < end; ++i) sum += values[i];
    return sum / static_cast<double>(window);
}
}  // namespace

VolumeSurge::VolumeSurge(std::size_t window, double sigma_multiplier)
    : window_(window), k_(sigma_multiplier),
      last_threshold_(std::numeric_limits<double>::infinity()) {
    if (window_ < 2 || !std::isfinite(k_) || k_ < 0.0)
        throw std::invalid_argument("window must be >= 2 and k finite/nonnegative");
}

bool VolumeSurge::observe(double volume) {
    if (!std::isfinite(volume) || volume < 0.0)
        throw std::invalid_argument("volume must be finite and nonnegative");

    bool surge = false;
    last_threshold_ = std::numeric_limits<double>::infinity();
    if (values_.size() >= window_) {
        double mean = 0.0;
        double m2 = 0.0;
        std::size_t n = 0;
        // Recompute reference statistics from prior observations only.
        for (const double x : values_) {
            ++n;
            const double delta = x - mean;
            mean += delta / static_cast<double>(n);
            m2 += delta * (x - mean);
        }
        const double variance = m2 / static_cast<double>(n); // population sigma
        last_threshold_ = mean + k_ * std::sqrt(std::max(0.0, variance));
        surge = volume > last_threshold_;
    }

    values_.push_back(volume);
    if (values_.size() > window_) values_.pop_front();
    return surge;
}

double VolumeSurge::threshold() const { return last_threshold_; }
std::size_t VolumeSurge::samples() const noexcept { return values_.size(); }

Signal evaluate_cross(const std::vector<double>& closes,
                      const std::vector<double>& benchmark_closes,
                      std::size_t fast_window,
                      std::size_t slow_window,
                      bool volume_surge,
                      bool sideline_lockdown) {
    Signal out;
    if (fast_window == 0 || slow_window <= fast_window ||
        closes.size() < slow_window + 1 ||
        benchmark_closes.size() < 2) return out;

    for (const double x : closes)
        if (!finite_positive(x)) { out.reason = "invalid_asset_prices"; return out; }
    for (const double x : benchmark_closes)
        if (!finite_positive(x)) { out.reason = "invalid_benchmark_prices"; return out; }

    const std::size_t n = closes.size();
    const double fast_prev = mean_tail(closes, n - 1, fast_window);
    const double slow_prev = mean_tail(closes, n - 1, slow_window);
    const double fast_now = mean_tail(closes, n, fast_window);
    const double slow_now = mean_tail(closes, n, slow_window);
    const double benchmark_delta =
        benchmark_closes.back() - benchmark_closes[benchmark_closes.size() - 2];

    if (sideline_lockdown) { out.reason = "sideline_lockdown"; return out; }
    if (!volume_surge) { out.reason = "volume_not_confirmed"; return out; }

    if (fast_prev <= slow_prev && fast_now > slow_now && benchmark_delta > 0.0) {
        out.direction = 1;
        out.approved = true;
        out.reason = "long_cross_volume_benchmark_confirmed";
    } else if (fast_prev >= slow_prev && fast_now < slow_now && benchmark_delta < 0.0) {
        out.direction = -1;
        out.reason = "short_signal_not_enabled_cash_only";
    } else {
        out.reason = "no_aligned_cross";
    }
    return out;
}

BasketDecision approve_cash_basket(const BasketLimits& limits,
                                   const std::vector<BasketProposal>& proposals) {
    BasketDecision out;
    if (!finite_positive(limits.equity) || proposals.empty() ||
        !std::isfinite(limits.max_basket_fraction) ||
        !std::isfinite(limits.max_asset_fraction) ||
        !std::isfinite(limits.max_asset_risk_fraction) ||
        !std::isfinite(limits.max_basket_risk_fraction) ||
        limits.max_basket_fraction <= 0.0 || limits.max_basket_fraction > 1.0 ||
        limits.max_asset_fraction <= 0.0 ||
        limits.max_asset_fraction > limits.max_basket_fraction ||
        limits.max_asset_risk_fraction <= 0.0 ||
        limits.max_basket_risk_fraction <= 0.0 || limits.max_assets == 0) {
        out.reason = "invalid_limits";
        return out;
    }

    if (proposals.size() > limits.max_assets) {
        out.reason = "basket_asset_count_exceeded";
        return out;
    }
    std::unordered_set<std::string> symbols;
    for (const auto& p : proposals) {
        if (p.symbol.empty() || !symbols.insert(p.symbol).second ||
            !finite_positive(p.entry) || !finite_positive(p.stop) ||
            p.stop >= p.entry || !finite_positive(p.requested_notional)) {
            out.reason = "invalid_or_duplicate_long_proposal";
            return out;
        }
        const double notional_cap = limits.equity * limits.max_asset_fraction;
        const double risk_cap = limits.equity * limits.max_asset_risk_fraction;
        const double stop_fraction = (p.entry - p.stop) / p.entry;
        const double max_by_risk = risk_cap / stop_fraction;
        if (p.requested_notional > std::min(notional_cap, max_by_risk) + 1e-9) {
            out.reason = "asset_allocation_or_stop_risk_exceeded";
            return out;
        }
        out.total_notional += p.requested_notional;
        out.planned_loss += p.requested_notional * stop_fraction;
    }
    if (out.total_notional > limits.equity * limits.max_basket_fraction + 1e-9) {
        out.reason = "basket_allocation_exceeded";
        return out;
    }
    if (out.planned_loss > limits.equity * limits.max_basket_risk_fraction + 1e-9) {
        out.reason = "basket_risk_exceeded";
        return out;
    }
    out.approved = true;
    out.reason = "cash_risk_limits_passed";
    return out;
}
}  // namespace quant::biberion
