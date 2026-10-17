#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>
namespace nb = nanobind;
using namespace nanobind::literals;

nb::dict risk_size(double p, double win, double loss, double cost, double equity,
                   double entry, double stop, double multiplier,
                   double risk_cap = 0.02, double fractional_kelly = 0.25) {
  const double vals[] = {p, win, loss, cost, equity, entry, stop, multiplier, risk_cap, fractional_kelly};
  for (double v : vals) if (!std::isfinite(v)) throw std::invalid_argument("NONFINITE_INPUT");
  if (p < 0 || p > 1 || win <= 0 || loss <= 0 || cost < 0 || equity <= 0 || entry <= 0 || stop <= 0 || entry == stop || multiplier <= 0 || risk_cap <= 0 || risk_cap > 0.02 || fractional_kelly <= 0 || fractional_kelly > 1)
    throw std::invalid_argument("INVALID_RISK_INPUT");
  const double ev = p * win - (1.0 - p) * loss - cost;
  nb::dict out;
  out["version"] = "QROS_RESEARCH_CONTROLS_V1";
  out["net_expectancy"] = ev;
  out["execution_authorized"] = false;
  if (ev <= 0) {
    out["status"] = "NO_TRADE"; out["reason"] = "NON_POSITIVE_NET_EXPECTANCY";
    out["full_kelly_fraction"] = 0.0; out["quarter_kelly_fraction"] = 0.0;
    out["risk_budget"] = 0.0; out["position_size"] = 0.0; return out;
  }
  const double win_net = win - cost, loss_net = loss + cost;
  if (win_net <= 0) {
    out["status"] = "NO_TRADE"; out["reason"] = "COSTS_ERASE_WIN_PAYOFF";
    out["full_kelly_fraction"] = 0.0; out["quarter_kelly_fraction"] = 0.0;
    out["risk_budget"] = 0.0; out["position_size"] = 0.0; return out;
  }
  const double full = std::max(0.0, p - (1.0 - p) / (win_net / loss_net));
  const double quarter = full * fractional_kelly;
  const double final_fraction = std::min(quarter, risk_cap);
  const double risk_budget = equity * final_fraction;
  const double per_unit_risk = std::abs(entry - stop) * multiplier + cost;
  if (!std::isfinite(per_unit_risk) || per_unit_risk <= 0) throw std::invalid_argument("INVALID_STOP_RISK");
  out["status"] = "CANDIDATE_FOR_RESEARCH_REVIEW"; out["reason"] = "POSITIVE_NET_EXPECTANCY_WITHIN_RISK_CAP";
  out["full_kelly_fraction"] = full; out["quarter_kelly_fraction"] = quarter;
  out["final_risk_fraction"] = final_fraction; out["risk_budget"] = risk_budget;
  out["stop_risk_per_unit"] = per_unit_risk; out["position_size"] = risk_budget / per_unit_risk;
  return out;
}

std::vector<std::string> bnf_signals(const std::vector<double>& close, const std::vector<double>& volume,
                                     double capacity_cap = 15000000000.0, std::size_t window = 25,
                                     double strong = -0.35, double candidate = -0.20) {
  if (close.size() != volume.size()) throw std::invalid_argument("CLOSE_VOLUME_LENGTH_MISMATCH");
  if (!std::isfinite(capacity_cap) || capacity_cap <= 0 || window < 2 || !std::isfinite(strong) || !std::isfinite(candidate) || !(strong < candidate && candidate < 0)) throw std::invalid_argument("INVALID_BNF_CONFIG");
  std::vector<std::string> result(close.size(), "NO_TRADE");
  for (std::size_t i=0; i<close.size(); ++i) {
    if (!std::isfinite(close[i]) || close[i] <= 0 || !std::isfinite(volume[i]) || volume[i] < 0 || i+1 < window) continue;
    double sum=0; bool valid=true;
    for (std::size_t j=i+1-window; j<=i; ++j) { if (!std::isfinite(close[j]) || close[j] <= 0) { valid=false; break; } sum += close[j]; }
    if (!valid) continue;
    const double ma=sum/static_cast<double>(window);
    if (!std::isfinite(ma) || ma <= 0) continue;
    const double deviation=(close[i]-ma)/ma;
    const double turnover=close[i]*volume[i];
    if (deviation <= strong && turnover <= capacity_cap) result[i]="BUY_STRONG";
    else if (deviation <= candidate) result[i]="CANDIDATE";
  }
  return result;
}

NB_MODULE(qros_research_controls, m) {
  m.doc() = "QROS deterministic research-only risk sizing and BNF kernels";
  m.def("risk_size", &risk_size, "win_probability"_a, "average_win"_a, "average_loss"_a,
        "cost_per_unit"_a, "equity"_a, "entry_price"_a, "stop_loss_price"_a,
        "contract_multiplier"_a, "risk_limit_fraction"_a=0.02, "fractional_kelly"_a=0.25);
  m.def("bnf_signals", &bnf_signals, "close"_a, "volume"_a, "capacity_cap"_a=15000000000.0,
        "window"_a=25, "strong_deviation"_a=-0.35, "candidate_deviation"_a=-0.20);
}
