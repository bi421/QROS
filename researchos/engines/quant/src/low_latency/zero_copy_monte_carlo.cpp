#include "quant/low_latency/zero_copy_monte_carlo.h"
#include <cmath>
#include <cstdint>
#include <stdexcept>
#if defined(_OPENMP)
#include <omp.h>
#endif
#if defined(QROS_AVX2) || defined(__AVX2__)
#include <immintrin.h>
#endif
namespace quant::low_latency {
namespace {
double sum_shocks(const double* row, std::size_t n) noexcept {
  double sum=0.0;
#if defined(QROS_AVX2) || defined(__AVX2__)
  std::size_t i=0;
  __m256d acc=_mm256_setzero_pd();
  for (;i+4<=n;i+=4) acc=_mm256_add_pd(acc,_mm256_loadu_pd(row+i));
  alignas(32) double lanes[4];
  _mm256_store_pd(lanes,acc);
  sum=lanes[0]+lanes[1]+lanes[2]+lanes[3];
  for (;i<n;++i) sum+=row[i];
#else
  for (std::size_t i=0;i<n;++i) sum+=row[i];
#endif
  return sum;
}
}
void ZeroCopyMonteCarlo::gbm_terminal_from_shocks(const double* shocks,std::size_t paths,
                                                   std::size_t steps,const GBMTerminalConfig& c,
                                                   double* out) {
  if (paths==0) return;
  if (!shocks || !out) throw std::invalid_argument("ZeroCopyMonteCarlo received a null buffer");
  if (!(c.spot>0.0) || !(c.volatility>=0.0) || !(c.time_horizon>=0.0) || steps==0)
    throw std::invalid_argument("invalid GBM configuration");
  const double dt=c.dt>0.0 ? c.dt : c.time_horizon/static_cast<double>(steps);
  if (!(dt>0.0)) throw std::invalid_argument("dt must be positive");
  const double sigma2=c.volatility*c.volatility;
  const double drift=(c.drift-0.5*sigma2)*c.time_horizon;
  const double scale=c.volatility*std::sqrt(dt);
#if defined(_OPENMP)
#pragma omp parallel for schedule(static)
#endif
  for (std::int64_t p=0;p<static_cast<std::int64_t>(paths);++p) {
    const double* row=shocks+static_cast<std::size_t>(p)*steps;
    out[p]=c.spot*std::exp(drift+scale*sum_shocks(row,steps));
  }
}
}  // namespace quant::low_latency
