#include "quant/low_latency/bayesian_signal_filter.h"
#include <cmath>
#include <stdexcept>
namespace quant::low_latency {
namespace {
constexpr double kEps = 1e-15;
double clamp_p(double p) noexcept { return p < kEps ? kEps : (p > 1.0-kEps ? 1.0-kEps : p); }
double logit(double p) noexcept { const double q=clamp_p(p); return std::log(q)-std::log1p(-q); }
double sigmoid(double x) noexcept {
  if (x >= 0.0) { const double e=std::exp(-x); return 1.0/(1.0+e); }
  const double e=std::exp(x); return e/(1.0+e);
}
}
void BayesianSignalFilter::filter_binary(const double* signal, const double* up,
                                         const double* down, std::size_t count,
                                         double prior, double* out) {
  if (count==0) return;
  if (!signal || !up || !down || !out) throw std::invalid_argument("BayesianSignalFilter received a null buffer");
  if (!(prior>0.0 && prior<1.0)) throw std::invalid_argument("prior_probability_up must be in (0, 1)");
  for (std::size_t i=0;i<count;++i) {
    if (!(up[i]>0.0 && up[i]<1.0 && down[i]>0.0 && down[i]<1.0))
      throw std::invalid_argument("likelihood probabilities must be in (0, 1)");
    if (!(signal[i]==0.0 || signal[i]==1.0))
      throw std::invalid_argument("binary signal values must be exactly 0 or 1");
  }
  double log_odds=logit(prior);
  for (std::size_t i=0;i<count;++i) {
    const bool positive=signal[i]==1.0;
    const double lu=positive ? up[i] : 1.0-up[i];
    const double ld=positive ? down[i] : 1.0-down[i];
    log_odds += std::log(lu)-std::log(ld);
    out[i]=sigmoid(log_odds);
  }
}
}  // namespace quant::low_latency
