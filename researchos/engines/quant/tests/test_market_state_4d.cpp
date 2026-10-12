#include <gtest/gtest.h>
#include "quant/market/market_state_4d.h"
#include <array>
#include <stdexcept>

TEST(MarketState4D, DerivesLatencyFromDualTimestamps) {
  const std::array<double,2> price{2300.0,2300.1};
  const std::array<double,2> volume{2.0,3.0};
  const std::array<std::int64_t,2> event{1'800'000'000'000'000'000LL,1'800'000'000'010'000'000LL};
  const std::array<std::int64_t,2> ingest{1'800'000'000'005'000'000LL,1'800'000'000'012'000'000LL};
  auto out=quant::market_state_4d::build_points({price.data(),volume.data(),event.data(),ingest.data(),2});
  ASSERT_EQ(out.size(),2U);
  EXPECT_DOUBLE_EQ(out[0].latency_ms,5.0);
  EXPECT_DOUBLE_EQ(out[1].latency_ms,2.0);
  EXPECT_DOUBLE_EQ(out[0].price,2300.0);
}

TEST(MarketState4D, RejectsInvalidPriceAndExcessiveClockSkew) {
  const std::array<double,1> price{0.0}, volume{1.0};
  const std::array<std::int64_t,1> event{100'000'000LL}, ingest{101'000'000LL};
  EXPECT_THROW(quant::market_state_4d::build_points({price.data(),volume.data(),event.data(),ingest.data(),1}),std::invalid_argument);
  const std::array<double,1> good_price{1.0};
  const std::array<std::int64_t,1> old_ingest{98'000'000LL};
  EXPECT_THROW(quant::market_state_4d::build_points({good_price.data(),volume.data(),event.data(),old_ingest.data(),1},1.0),std::invalid_argument);
}
