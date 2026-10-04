#include <gtest/gtest.h>
#include "quant/low_latency/bayesian_signal_filter.h"
#include "quant/low_latency/zero_copy_monte_carlo.h"
#include "quant/low_latency/candle_geometry.h"
#include "quant/low_latency/geometric_null.h"
#include "quant/low_latency/empirical_edge.h"
#include "quant/low_latency/diffusion_models.h"
#include "quant/low_latency/ornstein_uhlenbeck.h"
#include "quant/low_latency/market_dynamics.h"
#include "quant/low_latency/shannon_entropy.h"
#include <cmath>
#include <stdexcept>

namespace { constexpr double kPi = 3.141592653589793238462643383279502884; }

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

TEST(LowLatencyCandleGeometryTest, ComputesRatios) {
  const double o[]={97,90},h[]={100,100},l[]={90,80},c[]={98,85};
  double out[10]{};
  CandleGeometryKernel::compute(o,h,l,c,2,out);
  EXPECT_DOUBLE_EQ(10.0,out[0]);
  EXPECT_DOUBLE_EQ(.1,out[1]);
  EXPECT_DOUBLE_EQ(.2,out[2]);
  EXPECT_DOUBLE_EQ(.7,out[3]);
  EXPECT_DOUBLE_EQ(.8,out[4]);
  EXPECT_DOUBLE_EQ(20.0,out[5]);
  EXPECT_DOUBLE_EQ(.25,out[6]);
  EXPECT_DOUBLE_EQ(.25,out[7]);
  EXPECT_DOUBLE_EQ(.25,out[8]);
  EXPECT_DOUBLE_EQ(.25,out[9]);
}
TEST(LowLatencyGeometricNullTest, ComputesIntervalAndFirstPassage) {
  const double l[]={90},h[]={100},p1[]={90},p2[]={92},o[]={97};
  double interval[1]{}, high[1]{}, low[1]{};
  GeometricNullKernel::interval_probability(l,h,p1,p2,1,interval);
  GeometricNullKernel::first_passage(o,h,l,1,high,low);
  EXPECT_DOUBLE_EQ(.2,interval[0]);
  EXPECT_DOUBLE_EQ(.7,high[0]);
  EXPECT_DOUBLE_EQ(.3,low[0]);
}
TEST(LowLatencyEmpiricalEdgeTest, ComputesDeltaAndNullPValue) {
  const double empirical[]={.80}, geometric[]={.70}, n[]={100};
  double out[5]{};
  EmpiricalEdgeKernel::compute(empirical,geometric,n,1,out);
  EXPECT_DOUBLE_EQ(.80,out[0]);
  EXPECT_DOUBLE_EQ(.70,out[1]);
  EXPECT_DOUBLE_EQ(.10,out[2]);
  EXPECT_NEAR(2.1821789023599236,out[3],1e-12);
  EXPECT_NEAR(.0291363370103729,out[4],1e-12);
}
TEST(LowLatencyCandleGeometryTest, RejectsInvalidOHLC) {
  const double o[]={101},h[]={100},l[]={90},c[]={95}; double out[5]{};
  EXPECT_THROW(CandleGeometryKernel::compute(o,h,l,c,1,out),std::invalid_argument);
}

TEST(LowLatencyEmpiricalEdgeTest, RejectsDegenerateNullProbability) {
  const double empirical[]={0.10}, geometric[]={0.0}, n[]={100};
  double out[5]{};
  EXPECT_THROW(EmpiricalEdgeKernel::compute(empirical,geometric,n,1,out),std::invalid_argument);
}

TEST(LowLatencyDiffusionTest, HeatKernelAndGBMDensity) {
  const double x[]={0,1}, mean[]={0,0}, diffusion[]={.5,.5}, time[]={1,1};
  double out[2]{};
  DiffusionModelKernel::heat_density(x,mean,diffusion,time,2,out);
  EXPECT_NEAR(1.0/std::sqrt(2.0*kPi),out[0],1e-14);
  EXPECT_NEAR(std::exp(-.5)/std::sqrt(2.0*kPi),out[1],1e-14);

  const double spot[]={100}, price[]={100}, drift[]={.05}, vol[]={.2}, t[]={1};
  double gbm[1]{};
  DiffusionModelKernel::gbm_lognormal_density(spot,price,drift,vol,t,1,gbm);
  EXPECT_GT(gbm[0],0.0);
}

TEST(LowLatencyOUTest, MeanReversionMomentsAndInterval) {
  const double x0[]={110}, theta[]={1}, mu[]={100}, sigma[]={2}, time[]={1};
  double moments[2]{};
  OrnsteinUhlenbeckKernel::transition_moments(x0,theta,mu,sigma,time,1,moments);
  EXPECT_NEAR(100.0+10.0*std::exp(-1.0),moments[0],1e-14);
  EXPECT_NEAR(4.0*(1.0-std::exp(-2.0))/2.0,moments[1],1e-14);

  const double lower[]={100}, upper[]={105};
  double probability[1]{};
  OrnsteinUhlenbeckKernel::interval_probability(
      x0,theta,mu,sigma,time,lower,upper,1,probability);
  EXPECT_GT(probability[0],0.0);
  EXPECT_LT(probability[0],1.0);
}

TEST(LowLatencyMarketDynamicsTest, MomentumAndForce) {
  const double delta[]={2,-1}, volume[]={10,20}, dt[]={1,.5};
  double vm[4]{};
  MarketDynamicsKernel::velocity_momentum(delta,volume,dt,2,vm);
  EXPECT_DOUBLE_EQ(2.0,vm[0]);
  EXPECT_DOUBLE_EQ(20.0,vm[1]);
  EXPECT_DOUBLE_EQ(-2.0,vm[2]);
  EXPECT_DOUBLE_EQ(-40.0,vm[3]);

  const double momentum[]={20,-40}, previous[]={10,-20}, force_dt[]={2,2};
  double force[2]{};
  MarketDynamicsKernel::force(momentum,previous,force_dt,2,force);
  EXPECT_DOUBLE_EQ(5.0,force[0]);
  EXPECT_DOUBLE_EQ(-10.0,force[1]);
}

TEST(LowLatencyEntropyTest, ShannonEntropy) {
  const double probabilities[]={.5,.5,1.0,0.0};
  double entropy[2]{};
  double normalized[2]{};
  ShannonEntropyKernel::entropy(probabilities,2,2,entropy);
  ShannonEntropyKernel::normalized_entropy(probabilities,2,2,normalized);
  EXPECT_NEAR(std::log(2.0),entropy[0],1e-14);
  EXPECT_DOUBLE_EQ(0.0,entropy[1]);
  EXPECT_DOUBLE_EQ(1.0,normalized[0]);
  EXPECT_DOUBLE_EQ(0.0,normalized[1]);
}
