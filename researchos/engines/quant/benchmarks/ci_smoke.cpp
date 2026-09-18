#include "quant/backtest/market_data.h"
#include "quant/market/ohlcv_container.h"

#include <chrono>
#include <cstdio>
#include <vector>

int main() {
  constexpr std::size_t kRows = 10'000;
  const auto epoch = std::chrono::system_clock::from_time_t(0);

  std::vector<quant::Candle> candles;
  candles.reserve(kRows);
  for (std::size_t i = 0; i < kRows; ++i) {
    quant::Candle c;
    c.timestamp = epoch + std::chrono::minutes(static_cast<long long>(i));
    c.timeframe = quant::Timeframe::M1;
    c.open = 100.0 + static_cast<double>(i) * 0.001;
    c.high = c.open + 0.01;
    c.low = c.open - 0.01;
    c.close = c.open + 0.005;
    c.volume = 1000.0;
    c.trade_count = 1;
    candles.push_back(c);
  }

  quant::OHLCVContainer container("CI_SMOKE", quant::Timeframe::M1);
  for (const auto& candle : candles) {
    const auto result = container.append(candle);
    if (result.is_err()) {
      std::fprintf(stderr, "append failed: %s\n", result.error().message().c_str());
      return 1;
    }
  }

  quant::MarketData market_data;
  const auto loaded = market_data.load("CI_SMOKE", quant::Timeframe::M1, candles);
  if (loaded.is_err()) {
    std::fprintf(stderr, "market-data load failed: %s\n", loaded.error().message().c_str());
    return 1;
  }

  std::printf("ci_smoke,rows,%zu\n", kRows);
  return 0;
}
