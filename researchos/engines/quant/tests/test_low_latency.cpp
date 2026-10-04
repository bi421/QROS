#include <gtest/gtest.h>
#include "quant/low_latency/bayesian_signal_filter.h"
#include "quant/low_latency/zero_copy_monte_carlo.h"
#include <cmath>
using namespace quant::low_latency;
TEST(LowLatencyBayesianTest, MatchesSequentialBayesUpdate) {
  const double s[]={1,0,1}, up[]={.70,.20,.80}, down[]={.30,.60,.40}; double out[3]{};
  BayesianSignalFilter::filter_binary(s,up,down,3,.50,out);
  double expected=.50;
  for(int i=0;i<3;++i){ const double lu=s[i]==1?up[i]:1-up[i]; const double ld=s[i]==1?down[i]:1-down[i];
    expected=expected*lu/(expected*lu+(1-expected)*ld); EXPECT_NEAR(expected,out[i],1e-14); }
}
TEST(LowLatencyBayesianTest, RejectsInvalidLikelihood) {
  const double s[]={1},up[]={1},down[]={.5}; double out[1]{};
  EXPECT_THROW(BayesianSignalFilter::filter_binary(s,up,down,1,.5,out),std::invalid_argument);
}
TEST(LowLatencyMonteCarloTest, ZeroShockMatchesClosedForm) {
  const double z[]={0,0,0,0}; double out[2]{};
  GBMTerminalConfig c; c.spot=100;c.drift=.05;c.volatility=.2;c.time_horizon=1;
  ZeroCopyMonteCarlo::gbm_terminal_from_shocks(z,2,2,c,out);
  const double expected=100*std::exp(.05-.5*.2*.2);
  EXPECT_DOUBLE_EQ(expected,out[0]); EXPECT_DOUBLE_EQ(expected,out[1]);
}
TEST(LowLatencyMonteCarloTest, UsesCallerOwnedBuffers) {
  const double z[]={1,-1,.5,-.5}; double out[2]={-1,-1}; GBMTerminalConfig c; c.spot=100;c.drift=0;c.volatility=.2;c.time_horizon=1;
  ZeroCopyMonteCarlo::gbm_terminal_from_shocks(z,2,2,c,out);
  EXPECT_GT(out[0],0); EXPECT_GT(out[1],0); EXPECT_NE(-1,out[0]); EXPECT_NE(-1,out[1]);
}
