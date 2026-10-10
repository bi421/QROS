// BridgeBackend — the stable implementation of the Python/C++ integration
// contract (IBridgeBackend). Owns no global state; every call is pure and
// deterministic. See python/bridge_interface.h for the contract and
// python/bridge_models.h for the hash/canonical serialization rules.

#include "bridge_interface.h"
#include "bridge_models.h"
#include "bridge_validation.h"

#include "quant/backtest/backtest_engine.h"
#include "quant/backtest/market_data.h"
#include "quant/backtest/performance.h"
#include "quant/backtest/performance_analyzer.h"
#include "quant/backtest/serialization.h"
#include "quant/core/engine.h"
#include "quant/market/candle.h"
#include "quant/statistics/descriptive.h"
#include "quant/statistics/risk.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <functional>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace quant::bridge {

// ── Error model ────────────────────────────────────────────────────────────

const char* bridge_error_name(BridgeErrorCode code) {
  switch (code) {
    case BridgeErrorCode::None: return "None";
    case BridgeErrorCode::InvalidArgument: return "InvalidArgument";
    case BridgeErrorCode::InvalidParameter: return "InvalidParameter";
    case BridgeErrorCode::InvalidType: return "InvalidType";
    case BridgeErrorCode::InsufficientData: return "InsufficientData";
    case BridgeErrorCode::EmptyData: return "EmptyData";
    case BridgeErrorCode::MalformedData: return "MalformedData";
    case BridgeErrorCode::OutOfBounds: return "OutOfBounds";
    case BridgeErrorCode::UnsupportedVersion: return "UnsupportedVersion";
    case BridgeErrorCode::ValidationFailed: return "ValidationFailed";
    case BridgeErrorCode::HashMismatch: return "HashMismatch";
    case BridgeErrorCode::InternalError: return "InternalError";
  }
  return "Unknown";
}

BridgeError::BridgeError(BridgeErrorCode code, std::string message)
    : std::runtime_error(std::string("[") + bridge_error_name(code) + "] " + message),
      code_(code) {}

bool is_supported_calculation_version(const std::string& v) {
  const auto& versions = supported_calculation_versions();
  return std::find(versions.begin(), versions.end(), v) != versions.end();
}

BridgeMeta BridgeMeta::current() {
  BridgeMeta m;
  m.engine_version = Version::current().to_string();
  return m;
}

std::string BridgeMeta::to_json() const {
  return canonical_object({
      {"engine_name", "\"" + canonical_json_escape(engine_name) + "\""},
      {"engine_version", "\"" + canonical_json_escape(engine_version) + "\""},
      {"bridge_version", "\"" + canonical_json_escape(bridge_version) + "\""},
      {"protocol_version", canonical_float(static_cast<double>(protocol_version))},
      {"calculation_version", "\"" + canonical_json_escape(calculation_version) + "\""},
  });
}

// ── Canonical serialization ────────────────────────────────────────────────
// The exact byte layout produced here is reproduced by
// python/cpp_quant_engine/models.py (canonical_* helpers) so that hashes are
// identical across languages.

std::string canonical_float(double v) {
  char buf[128];
  std::snprintf(buf, sizeof(buf), "%.10f", v);
  return std::string(buf);
}

std::string canonical_json_escape(const std::string& s) {
  std::string out;
  out.reserve(s.size() + 2);
  for (unsigned char c : s) {
    switch (c) {
      case '"': out += "\\\""; break;
      case '\\': out += "\\\\"; break;
      case '\b': out += "\\b"; break;
      case '\f': out += "\\f"; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default:
        if (c < 0x20) {
          char buf[7];
          std::snprintf(buf, sizeof(buf), "\\u%04x", static_cast<unsigned>(c));
          out += buf;
        } else {
          out += static_cast<char>(c);
        }
    }
  }
  return out;
}

std::string canonical_object(
    std::initializer_list<std::pair<std::string, std::string>> fields) {
  std::vector<std::pair<std::string, std::string>> sorted(fields.begin(), fields.end());
  std::sort(sorted.begin(), sorted.end(),
            [](const auto& a, const auto& b) { return a.first < b.first; });
  std::string out = "{";
  bool first = true;
  for (const auto& [key, value] : sorted) {
    if (!first) out += ',';
    first = false;
    out += '"';
    out += canonical_json_escape(key);
    out += "\":";
    out += value;
  }
  out += '}';
  return out;
}

std::string canonical_float_array(const std::vector<double>& values) {
  std::string out = "[";
  for (size_t i = 0; i < values.size(); ++i) {
    if (i) out += ',';
    out += canonical_float(values[i]);
  }
  out += ']';
  return out;
}

std::string canonical_string_array(const std::vector<std::string>& values) {
  std::string out = "[";
  for (size_t i = 0; i < values.size(); ++i) {
    if (i) out += ',';
    out += '"';
    out += canonical_json_escape(values[i]);
    out += '"';
  }
  out += ']';
  return out;
}

std::string canonical_double_map(const std::unordered_map<std::string, double>& m) {
  std::vector<std::pair<std::string, std::string>> entries;
  entries.reserve(m.size());
  for (const auto& [k, v] : m) {
    entries.emplace_back(k, canonical_float(v));
  }
  std::sort(entries.begin(), entries.end(),
            [](const auto& a, const auto& b) { return a.first < b.first; });
  std::string out = "{";
  bool first = true;
  for (const auto& [k, v] : entries) {
    if (!first) out += ',';
    first = false;
    out += '"';
    out += canonical_json_escape(k);
    out += "\":";
    out += v;
  }
  out += '}';
  return out;
}

// ── SHA-256 ────────────────────────────────────────────────────────────────

namespace {

using u32 = uint32_t;

constexpr u32 kSha256K[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u,
    0x923f82a4u, 0xab1c5ed5u, 0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
    0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u, 0xe49b69c1u, 0xefbe4786u,
    0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
    0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u,
    0x06ca6351u, 0x14292967u, 0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
    0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u, 0xa2bfe8a1u, 0xa81a664bu,
    0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
    0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au,
    0x5b9cca4fu, 0x682e6ff3u, 0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
    0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u};

inline u32 rot_r(u32 x, int n) { return (x >> n) | (x << (32 - n)); }

struct Sha256 {
  u32 h[8] = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
              0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
  unsigned char block[64];
  size_t block_len = 0;
  uint64_t total = 0;

  void compress(const unsigned char* p) {
    u32 w[64];
    for (int i = 0; i < 16; ++i) {
      w[i] = (static_cast<u32>(p[i * 4]) << 24) |
             (static_cast<u32>(p[i * 4 + 1]) << 16) |
             (static_cast<u32>(p[i * 4 + 2]) << 8) |
             static_cast<u32>(p[i * 4 + 3]);
    }
    for (int i = 16; i < 64; ++i) {
      u32 s0 = rot_r(w[i - 15], 7) ^ rot_r(w[i - 15], 18) ^ (w[i - 15] >> 3);
      u32 s1 = rot_r(w[i - 2], 17) ^ rot_r(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    u32 a = h[0], b = h[1], c = h[2], d = h[3];
    u32 e = h[4], f = h[5], g = h[6], hh = h[7];
    for (int i = 0; i < 64; ++i) {
      u32 S1 = rot_r(e, 6) ^ rot_r(e, 11) ^ rot_r(e, 25);
      u32 ch = (e & f) ^ (~e & g);
      u32 t1 = hh + S1 + ch + kSha256K[i] + w[i];
      u32 S0 = rot_r(a, 2) ^ rot_r(a, 13) ^ rot_r(a, 22);
      u32 maj = (a & b) ^ (a & c) ^ (b & c);
      u32 t2 = S0 + maj;
      hh = g; g = f; f = e; e = d + t1;
      d = c; c = b; b = a; a = t1 + t2;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d;
    h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
  }

  void update(const void* data, size_t n) {
    const auto* bytes = static_cast<const unsigned char*>(data);
    total += n;
    while (n > 0) {
      size_t take = 64 - block_len;
      if (take > n) take = n;
      std::memcpy(block + block_len, bytes, take);
      block_len += take;
      bytes += take;
      n -= take;
      if (block_len == 64) {
        compress(block);
        block_len = 0;
      }
    }
  }

  void final(unsigned char out[32]) {
    uint64_t bit_len = total * 8;
    unsigned char pad = 0x80;
    update(&pad, 1);
    unsigned char zero = 0x00;
    while (block_len != 56) update(&zero, 1);
    unsigned char len_bytes[8];
    for (int i = 0; i < 8; ++i) {
      len_bytes[i] = static_cast<unsigned char>((bit_len >> (56 - i * 8)) & 0xff);
    }
    update(len_bytes, 8);
    for (int i = 0; i < 8; ++i) {
      out[i * 4] = static_cast<unsigned char>((h[i] >> 24) & 0xff);
      out[i * 4 + 1] = static_cast<unsigned char>((h[i] >> 16) & 0xff);
      out[i * 4 + 2] = static_cast<unsigned char>((h[i] >> 8) & 0xff);
      out[i * 4 + 3] = static_cast<unsigned char>(h[i] & 0xff);
    }
  }
};

} // namespace

std::string sha256_hex(const std::string& input) {
  Sha256 ctx;
  ctx.update(input.data(), input.size());
  unsigned char digest[32];
  ctx.final(digest);
  static const char* hex = "0123456789abcdef";
  std::string out;
  out.reserve(64);
  for (unsigned char b : digest) {
    out += hex[b >> 4];
    out += hex[b & 0x0f];
  }
  return out;
}

std::string iso8601_now() {
  const auto now = std::chrono::system_clock::now();
  const auto tt = std::chrono::system_clock::to_time_t(now);
  std::tm tm{};
#if defined(_MSC_VER)
  gmtime_s(&tm, &tt);
#else
  gmtime_r(&tt, &tm);
#endif
  // tm fields are integers with no strict upper width bound, so a small
  // fixed buffer can trigger -Wformat-truncation or silently truncate output.
  char buf[128];
  const int written = std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d",
                                    tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday,
                                    tm.tm_hour, tm.tm_min, tm.tm_sec);
  if (written < 0 || static_cast<std::size_t>(written) >= sizeof(buf)) {
    throw std::runtime_error("ISO-8601 timestamp formatting failed or truncated");
  }
  return std::string(buf, static_cast<std::size_t>(written));
}

// ── Model canonical forms / hashes ─────────────────────────────────────────

std::string CandleModel::to_canonical() const {
  return canonical_object({
      {"close", canonical_float(close)},
      {"high", canonical_float(high)},
      {"low", canonical_float(low)},
      {"open", canonical_float(open)},
      {"timeframe", "\"" + canonical_json_escape(timeframe) + "\""},
      {"timestamp", "\"" + canonical_json_escape(timestamp) + "\""},
      {"volume", canonical_float(volume)},
  });
}

std::string MarketDataRequest::compute_input_hash() const {
  std::string candles = "[";
  for (size_t i = 0; i < this->candles.size(); ++i) {
    if (i) candles += ',';
    candles += this->candles[i].to_canonical();
  }
  candles += ']';
  return sha256_hex(canonical_object({
      {"calculation_version", "\"" + canonical_json_escape(calculation_version) + "\""},
      {"candles", candles},
      {"symbol", "\"" + canonical_json_escape(symbol) + "\""},
      {"timeframe", "\"" + canonical_json_escape(timeframe) + "\""},
  }));
}

std::string MarketDataResult::compute_result_hash() const {
  return sha256_hex(canonical_object({
      {"bridge_version", "\"" + canonical_json_escape(bridge_version) + "\""},
      {"calculation_version", "\"" + canonical_json_escape(calculation_version) + "\""},
      {"engine_version", "\"" + canonical_json_escape(engine_version) + "\""},
      {"first_timestamp", "\"" + canonical_json_escape(first_timestamp) + "\""},
      {"input_hash", "\"" + canonical_json_escape(input_hash) + "\""},
      {"last_timestamp", "\"" + canonical_json_escape(last_timestamp) + "\""},
      {"size", canonical_float(static_cast<double>(size))},
      {"symbol", "\"" + canonical_json_escape(symbol) + "\""},
      {"timeframe", "\"" + canonical_json_escape(timeframe) + "\""},
      {"valid", valid ? "true" : "false"},
      {"validation_message", "\"" + canonical_json_escape(validation_message) + "\""},
  }));
}

std::string StatisticsRequest::compute_input_hash() const {
  return sha256_hex(canonical_object({
      {"calculation_version", "\"" + canonical_json_escape(calculation_version) + "\""},
      {"data", canonical_float_array(data)},
  }));
}

std::string StatisticsResult::compute_result_hash() const {
  return sha256_hex(canonical_object({
      {"bridge_version", "\"" + canonical_json_escape(bridge_version) + "\""},
      {"calculation_version", "\"" + canonical_json_escape(calculation_version) + "\""},
      {"count", canonical_float(static_cast<double>(count))},
      {"engine_version", "\"" + canonical_json_escape(engine_version) + "\""},
      {"input_hash", "\"" + canonical_json_escape(input_hash) + "\""},
      {"iqr", canonical_float(iqr)},
      {"kurtosis", canonical_float(kurtosis)},
      {"max", canonical_float(max)},
      {"mean", canonical_float(mean)},
      {"median", canonical_float(median)},
      {"min", canonical_float(min)},
      {"q1", canonical_float(q1)},
      {"q3", canonical_float(q3)},
      {"skewness", canonical_float(skewness)},
      {"stddev", canonical_float(stddev)},
      {"sum", canonical_float(sum)},
      {"variance", canonical_float(variance)},
  }));
}

std::string RiskRequest::compute_input_hash() const {
  return sha256_hex(canonical_object({
      {"calculation_version", "\"" + canonical_json_escape(calculation_version) + "\""},
      {"equity_curve", canonical_float_array(equity_curve)},
      {"returns", canonical_float_array(returns)},
      {"risk_free_rate", canonical_float(risk_free_rate)},
  }));
}

std::string RiskResult::compute_result_hash() const {
  return sha256_hex(canonical_object({
      {"bridge_version", "\"" + canonical_json_escape(bridge_version) + "\""},
      {"calculation_version", "\"" + canonical_json_escape(calculation_version) + "\""},
      {"cvar_95", canonical_float(cvar_95)},
      {"cvar_99", canonical_float(cvar_99)},
      {"engine_version", "\"" + canonical_json_escape(engine_version) + "\""},
      {"input_hash", "\"" + canonical_json_escape(input_hash) + "\""},
      {"max_drawdown_pct", canonical_float(max_drawdown_pct)},
      {"peak_index", canonical_float(static_cast<double>(peak_index))},
      {"recovery_index", canonical_float(static_cast<double>(recovery_index))},
      {"sharpe_ratio", canonical_float(sharpe_ratio)},
      {"sortino_ratio", canonical_float(sortino_ratio)},
      {"trough_index", canonical_float(static_cast<double>(trough_index))},
      {"var_95", canonical_float(var_95)},
      {"var_99", canonical_float(var_99)},
  }));
}

std::string SimulationRequest::compute_input_hash() const {
  return sha256_hex(canonical_object({
      {"calculation_version", "\"" + canonical_json_escape(calculation_version) + "\""},
      {"dataset_reference", "\"" + canonical_json_escape(dataset_reference) + "\""},
      {"dataset_version", "\"" + canonical_json_escape(dataset_version) + "\""},
      {"end_time", "\"" + canonical_json_escape(end_time) + "\""},
      {"initial_capital", canonical_float(initial_capital)},
      {"prices", canonical_float_array(prices)},
      {"risk_free_rate", canonical_float(risk_free_rate)},
      {"seed", canonical_float(static_cast<double>(seed))},
      {"start_time", "\"" + canonical_json_escape(start_time) + "\""},
  }));
}

std::string SimulationResult::compute_result_hash() const {
  return sha256_hex(canonical_object({
      {"bridge_version", "\"" + canonical_json_escape(bridge_version) + "\""},
      {"calculation_version", "\"" + canonical_json_escape(calculation_version) + "\""},
      {"dataset_reference", "\"" + canonical_json_escape(dataset_reference) + "\""},
      {"dataset_version", "\"" + canonical_json_escape(dataset_version) + "\""},
      {"end_time", "\"" + canonical_json_escape(end_time) + "\""},
      {"engine_version", "\"" + canonical_json_escape(engine_version) + "\""},
      {"equity_curve", canonical_float_array(equity_curve)},
      {"input_hash", "\"" + canonical_json_escape(input_hash) + "\""},
      {"metrics", canonical_double_map(metrics)},
      {"performance", canonical_double_map(performance)},
      {"returns", canonical_float_array(returns)},
      {"simulation_id", "\"" + canonical_json_escape(simulation_id) + "\""},
      {"start_time", "\"" + canonical_json_escape(start_time) + "\""},
      {"statistics", canonical_double_map(statistics)},
  }));
}

std::string BacktestRequest::compute_input_hash() const {
  std::string candles = "[";
  for (size_t i = 0; i < this->candles.size(); ++i) {
    if (i) candles += ',';
    candles += this->candles[i].to_canonical();
  }
  candles += ']';
  return sha256_hex(canonical_object({
      {"allow_short", allow_short ? "true" : "false"},
      {"calculation_version", "\"" + canonical_json_escape(calculation_version) + "\""},
      {"candles", candles},
      {"commission_pct", canonical_float(commission_pct)},
      {"initial_capital", canonical_float(initial_capital)},
      {"signal_reference", "\"" + canonical_json_escape(signal_reference) + "\""},
      {"slippage_pct", canonical_float(slippage_pct)},
      {"symbol", "\"" + canonical_json_escape(symbol) + "\""},
      {"timeframe", "\"" + canonical_json_escape(timeframe) + "\""},
  }));
}

std::string BacktestResult::compute_result_hash() const {
  return sha256_hex(canonical_object({
      {"bridge_version", "\"" + canonical_json_escape(bridge_version) + "\""},
      {"calculation_version", "\"" + canonical_json_escape(calculation_version) + "\""},
      {"drawdown_curve", canonical_float_array(drawdown_curve)},
      {"engine_version", "\"" + canonical_json_escape(engine_version) + "\""},
      {"equity_curve", canonical_float_array(equity_curve)},
      {"final_equity", canonical_float(final_equity)},
      {"input_hash", "\"" + canonical_json_escape(input_hash) + "\""},
      {"max_drawdown_pct", canonical_float(max_drawdown_pct)},
      {"num_trades", canonical_float(static_cast<double>(num_trades))},
      {"signal_reference", "\"" + canonical_json_escape(signal_reference) + "\""},
      {"total_bars", canonical_float(static_cast<double>(total_bars))},
      {"total_return_pct", canonical_float(total_return_pct)},
  }));
}

std::string PerformanceRequest::compute_input_hash() const {
  std::string bars = "[";
  for (size_t i = 0; i < this->bars.size(); ++i) {
    if (i) bars += ',';
    bars += this->bars[i].to_canonical();
  }
  bars += ']';
  return sha256_hex(canonical_object({
      {"bars", bars},
      {"calculation_version", "\"" + canonical_json_escape(calculation_version) + "\""},
      {"equity_curve", canonical_float_array(equity_curve)},
      {"initial_capital", canonical_float(initial_capital)},
      {"trading_days_per_year", canonical_float(trading_days_per_year)},
  }));
}

std::string PerformanceResult::compute_result_hash() const {
  return sha256_hex(canonical_object({
      {"annualized_return", canonical_float(annualized_return)},
      {"annualized_volatility", canonical_float(annualized_volatility)},
      {"bridge_version", "\"" + canonical_json_escape(bridge_version) + "\""},
      {"calmar_ratio", canonical_float(calmar_ratio)},
      {"calculation_version", "\"" + canonical_json_escape(calculation_version) + "\""},
      {"cvar_95", canonical_float(cvar_95)},
      {"cvar_99", canonical_float(cvar_99)},
      {"downside_deviation_annualized", canonical_float(downside_deviation_annualized)},
      {"engine_version", "\"" + canonical_json_escape(engine_version) + "\""},
      {"input_hash", "\"" + canonical_json_escape(input_hash) + "\""},
      {"losing_trades", canonical_float(static_cast<double>(losing_trades))},
      {"max_drawdown_pct", canonical_float(max_drawdown_pct)},
      {"max_drawdown_recovery_bars", canonical_float(static_cast<double>(max_drawdown_recovery_bars))},
      {"num_drawdown_periods", canonical_float(static_cast<double>(num_drawdown_periods))},
      {"num_monthly_periods", canonical_float(static_cast<double>(num_monthly_periods))},
      {"num_yearly_periods", canonical_float(static_cast<double>(num_yearly_periods))},
      {"profit_factor", canonical_float(profit_factor)},
      {"sharpe_ratio", canonical_float(sharpe_ratio)},
      {"sortino_ratio", canonical_float(sortino_ratio)},
      {"time_in_drawdown_pct", canonical_float(time_in_drawdown_pct)},
      {"total_return", canonical_float(total_return)},
      {"total_return_pct", canonical_float(total_return_pct)},
      {"total_trades", canonical_float(static_cast<double>(total_trades))},
      {"var_95", canonical_float(var_95)},
      {"var_99", canonical_float(var_99)},
      {"win_rate", canonical_float(win_rate)},
      {"winning_trades", canonical_float(static_cast<double>(winning_trades))},
  }));
}

// ── Internal helpers ───────────────────────────────────────────────────────

namespace {

Candle to_engine_candle(const CandleModel& c, Timeframe tf) {
  Candle out;
  out.timestamp = serialization::from_iso8601(c.timestamp);
  out.open = c.open;
  out.high = c.high;
  out.low = c.low;
  out.close = c.close;
  out.volume = c.volume;
  out.timeframe = tf;
  return out;
}

std::string engine_error_message(const Error& e) { return e.message(); }

// Percentage (simple) returns from a price series. Deterministic; returns a
// series of length n-1. Zero/negative previous prices yield 0.0 to keep the
// simulation well-defined.
std::vector<double> simple_returns(const std::vector<double>& prices) {
  std::vector<double> out;
  if (prices.size() < 2) return out;
  out.reserve(prices.size() - 1);
  for (size_t i = 1; i < prices.size(); ++i) {
    const double prev = prices[i - 1];
    out.push_back(prev != 0.0 ? (prices[i] - prev) / prev : 0.0);
  }
  return out;
}

std::vector<double> equity_from_capital(const std::vector<double>& prices,
                                        double capital) {
  std::vector<double> out;
  if (prices.empty()) return out;
  out.reserve(prices.size());
  double eq = capital;
  out.push_back(eq);
  for (size_t i = 1; i < prices.size(); ++i) {
    const double prev = prices[i - 1];
    eq *= (prev != 0.0) ? (prices[i] / prev) : 1.0;
    out.push_back(eq);
  }
  return out;
}

} // namespace

// ── BridgeBackend ──────────────────────────────────────────────────────────

class BridgeBackend : public IBridgeBackend {
public:
  BridgeMeta meta() const override { return BridgeMeta::current(); }

  std::string version() const override {
    return Version::current().to_string();
  }

  MarketDataResult market_data_load(const MarketDataRequest& req) override {
    validate_market_data_request(req);
    const auto tf_opt = timeframe_from_string(req.timeframe);
    const Timeframe tf = tf_opt.value_or(Timeframe::M1);

    MarketDataResult result;
    result.symbol = req.symbol;
    result.timeframe = req.timeframe;
    result.size = req.candles.size();
    result.calculation_version = req.calculation_version;
    result.engine_version = Version::current().to_string();
    result.bridge_version = kBridgeVersion;
    result.input_hash = req.compute_input_hash();

    MarketData md(MarketDataConfig{req.symbol, tf});
    std::vector<Candle> candles;
    candles.reserve(req.candles.size());
    for (const auto& c : req.candles) {
      candles.push_back(to_engine_candle(c, tf));
    }
    auto load = md.load(req.symbol, tf, candles);
    if (load.is_err()) {
      result.valid = false;
      result.validation_message = engine_error_message(load.error());
    } else {
      auto chk = md.validate();
      if (chk.is_err()) {
        result.valid = false;
        result.validation_message = engine_error_message(chk.error());
      } else {
        result.valid = true;
      }
    }
    result.first_timestamp = candles.empty() ? "" : serialization::to_iso8601(candles.front().timestamp);
    result.last_timestamp = candles.empty() ? "" : serialization::to_iso8601(candles.back().timestamp);
    result.result_hash = result.compute_result_hash();
    return result;
  }

  StatisticsResult statistics_compute(const StatisticsRequest& req) override {
    validate_statistics_request(req);

    auto stats = DescriptiveStats::compute(req.data);
    if (stats.is_err()) {
      throw BridgeError(BridgeErrorCode::InternalError,
                        "statistics: " + engine_error_message(stats.error()));
    }
    const auto& s = stats.value();
    StatisticsResult result;
    result.count = s.count;
    result.sum = s.sum;
    result.mean = s.mean;
    result.variance = s.variance;
    result.stddev = s.stddev;
    result.skewness = s.skewness;
    result.kurtosis = s.kurtosis;
    result.min = s.min;
    result.max = s.max;
    result.q1 = s.q1;
    result.median = s.median;
    result.q3 = s.q3;
    result.iqr = s.iqr;
    result.calculation_version = req.calculation_version;
    result.engine_version = Version::current().to_string();
    result.bridge_version = kBridgeVersion;
    result.input_hash = req.compute_input_hash();
    result.result_hash = result.compute_result_hash();
    return result;
  }

  RiskResult risk_compute(const RiskRequest& req) override {
    validate_risk_request(req);

    RiskResult result;
    result.calculation_version = req.calculation_version;
    result.engine_version = Version::current().to_string();
    result.bridge_version = kBridgeVersion;
    result.input_hash = req.compute_input_hash();

    auto var = RiskMetrics::value_at_risk(req.returns, 0.95, 0.99);
    if (var.is_ok()) {
      result.var_95 = var.value().var_95;
      result.var_99 = var.value().var_99;
      result.cvar_95 = var.value().cvar_95;
      result.cvar_99 = var.value().cvar_99;
    }

    auto dd = RiskMetrics::max_drawdown(req.equity_curve);
    if (dd.is_ok()) {
      result.max_drawdown_pct = dd.value().max_drawdown_pct;
      result.peak_index = dd.value().peak_index;
      result.trough_index = dd.value().trough_index;
      result.recovery_index = dd.value().recovery_index;
    }

    auto sharpe = RiskMetrics::sharpe_ratio(req.returns, req.risk_free_rate);
    if (sharpe.is_ok()) result.sharpe_ratio = sharpe.value();

    auto sortino = RiskMetrics::sortino_ratio(req.returns, req.risk_free_rate);
    if (sortino.is_ok()) result.sortino_ratio = sortino.value();

    result.result_hash = result.compute_result_hash();
    return result;
  }

  SimulationResult simulation_run(const SimulationRequest& req) override {
    validate_simulation_request(req);

    SimulationResult result;
    result.dataset_reference = req.dataset_reference;
    result.dataset_version = req.dataset_version;
    result.calculation_version = req.calculation_version;
    result.start_time = req.start_time;
    result.end_time = req.end_time;
    result.input_hash = req.compute_input_hash();
    result.simulation_id = "sim_" + result.input_hash.substr(0, 16);
    result.execution_timestamp = iso8601_now();
    result.engine_version = Version::current().to_string();
    result.bridge_version = kBridgeVersion;

    const auto returns = simple_returns(req.prices);
    result.returns = returns;
    result.equity_curve = equity_from_capital(req.prices, req.initial_capital);

    // Metrics.
    auto var = RiskMetrics::value_at_risk(returns, 0.95, 0.99);
    result.metrics["initial_capital"] = req.initial_capital;
    result.metrics["final_equity"] = result.equity_curve.back();
    result.metrics["total_return_pct"] =
        req.initial_capital != 0.0
            ? (result.equity_curve.back() - req.initial_capital) / req.initial_capital * 100.0
            : 0.0;
    if (var.is_ok()) {
      result.metrics["var_95"] = var.value().var_95;
      result.metrics["var_99"] = var.value().var_99;
      result.metrics["cvar_95"] = var.value().cvar_95;
      result.metrics["cvar_99"] = var.value().cvar_99;
    }
    if (auto sharpe = RiskMetrics::sharpe_ratio(returns, req.risk_free_rate); sharpe.is_ok())
      result.metrics["sharpe_ratio"] = sharpe.value();
    if (auto sortino = RiskMetrics::sortino_ratio(returns, req.risk_free_rate); sortino.is_ok())
      result.metrics["sortino_ratio"] = sortino.value();
    if (auto dd = RiskMetrics::max_drawdown(result.equity_curve); dd.is_ok())
      result.metrics["max_drawdown_pct"] = dd.value().max_drawdown_pct;

    // Statistics over returns.
    if (auto stats = DescriptiveStats::compute(returns); stats.is_ok()) {
      result.statistics["count"] = static_cast<double>(stats.value().count);
      result.statistics["mean"] = stats.value().mean;
      result.statistics["stddev"] = stats.value().stddev;
      result.statistics["skewness"] = stats.value().skewness;
      result.statistics["kurtosis"] = stats.value().kurtosis;
      result.statistics["min"] = stats.value().min;
      result.statistics["max"] = stats.value().max;
      result.statistics["median"] = stats.value().median;
    }

    // Performance over the equity curve.
    if (!result.equity_curve.empty()) {
      std::vector<double> eq_returns;
      eq_returns.reserve(result.equity_curve.size() - 1);
      for (size_t i = 1; i < result.equity_curve.size(); ++i) {
        const double prev = result.equity_curve[i - 1];
        if (prev != 0.0) eq_returns.push_back((result.equity_curve[i] - prev) / prev);
      }
      if (!eq_returns.empty()) {
        const double mean_ret = DescriptiveStats::mean_of(eq_returns);
        const double variance =
            DescriptiveStats::variance_of(eq_returns, mean_ret);
        const double stddev = std::sqrt(variance);
        result.performance["annualized_return"] = mean_ret * 252.0;
        result.performance["annualized_volatility"] = stddev * std::sqrt(252.0);
        size_t wins = 0;
        for (double r : eq_returns) if (r > 0.0) ++wins;
        result.performance["win_rate"] =
            static_cast<double>(wins) / static_cast<double>(eq_returns.size());
        double gain = 0.0, loss = 0.0;
        for (double r : eq_returns) {
          if (r > 0.0) gain += r;
          else if (r < 0.0) loss += -r;
        }
        result.performance["profit_factor"] = loss > 0.0 ? gain / loss : (gain > 0.0 ? 0.0 : 0.0);
      }
      auto dd = RiskMetrics::max_drawdown(result.equity_curve);
      if (dd.is_ok()) result.performance["max_drawdown_pct"] = dd.value().max_drawdown_pct;
    }

    result.result_hash = result.compute_result_hash();
    return result;
  }

  BacktestResult backtest_run(const BacktestRequest& req,
                              const BridgeSignalFn& signal) override {
    validate_backtest_request(req);
    const auto tf_opt = timeframe_from_string(req.timeframe);
    const Timeframe tf = tf_opt.value_or(Timeframe::M1);

    BacktestResult result;
    result.signal_reference = req.signal_reference;
    result.calculation_version = req.calculation_version;
    result.engine_version = Version::current().to_string();
    result.bridge_version = kBridgeVersion;
    result.input_hash = req.compute_input_hash();

    std::vector<Candle> candles;
    candles.reserve(req.candles.size());
    for (const auto& c : req.candles) candles.push_back(to_engine_candle(c, tf));

    MarketData md(MarketDataConfig{req.symbol, tf});
    auto load = md.load(req.symbol, tf, candles);
    if (load.is_err()) {
      throw BridgeError(BridgeErrorCode::ValidationFailed,
                        "backtest: " + engine_error_message(load.error()));
    }

    BacktestEngine engine;
    BacktestConfig cfg;
    cfg.initial_capital = req.initial_capital;
    cfg.commission_pct = req.commission_pct;
    cfg.slippage_pct = req.slippage_pct;
    cfg.allow_short = req.allow_short;
    engine.set_config(cfg);

    const auto noop = [](size_t, const std::vector<OHLCV>&) {
      return SignalResult{TradeDirection::Buy, 0.0, 0.0, 0.0};
    };
    const BridgeSignalFn& fn = signal ? signal : noop;

    auto run = engine.run(md, fn);
    if (run.is_err()) {
      throw BridgeError(BridgeErrorCode::InternalError,
                        "backtest: " + engine_error_message(run.error()));
    }
    const auto& bt = run.value();
    result.equity_curve = bt.equity_curve;
    result.drawdown_curve = bt.drawdown_curve;
    result.final_equity = bt.final_equity;
    result.total_return_pct = bt.total_return_pct;
    result.max_drawdown_pct = bt.max_drawdown_pct;
    result.total_bars = bt.total_bars;
    result.num_trades = bt.trade_book.trades().size();
    result.result_hash = result.compute_result_hash();
    return result;
  }

  PerformanceResult performance_analyze(const PerformanceRequest& req) override {
    validate_performance_request(req);

    PerformanceResult result;
    result.calculation_version = req.calculation_version;
    result.engine_version = Version::current().to_string();
    result.bridge_version = kBridgeVersion;
    result.input_hash = req.compute_input_hash();

    // Reconstruct a lightweight BacktestResult so engine analytics can run.
    quant::BacktestResult bt;
    bt.equity_curve = req.equity_curve;
    bt.config.initial_capital = req.initial_capital;
    bt.final_equity = req.equity_curve.empty() ? 0.0 : req.equity_curve.back();
    bt.total_return_pct =
        (req.initial_capital != 0.0 && !req.equity_curve.empty())
            ? (bt.final_equity - req.initial_capital) / req.initial_capital * 100.0
            : 0.0;
    std::vector<OHLCV> bars;
    bars.reserve(req.bars.size());
    for (const auto& c : req.bars) {
      bars.push_back(static_cast<OHLCV>(to_engine_candle(c, Timeframe::M1)));
    }
    bt.bars_used = bars;
    if (auto dd = RiskMetrics::max_drawdown(bt.equity_curve); dd.is_ok()) {
      bt.max_drawdown_pct = dd.value().max_drawdown_pct;
    }

    const auto report = quant::PerformanceReport::compute(bt, req.trading_days_per_year);
    result.total_return = report.total_return;
    result.total_return_pct = report.total_return_pct;
    result.annualized_return = report.annualized_return;
    result.annualized_volatility = report.annualized_volatility;
    result.sharpe_ratio = report.sharpe_ratio;
    result.sortino_ratio = report.sortino_ratio;
    result.calmar_ratio = report.calmar_ratio;
    result.max_drawdown_pct = report.max_drawdown_pct;
    result.win_rate = report.win_rate;
    result.profit_factor = report.profit_factor;
    result.downside_deviation_annualized = report.downside_deviation_annualized;
    result.var_95 = report.var_95;
    result.var_99 = report.var_99;
    result.cvar_95 = report.cvar_95;
    result.cvar_99 = report.cvar_99;
    result.time_in_drawdown_pct = report.time_in_drawdown_pct;
    result.total_trades = report.total_trades;
    result.winning_trades = report.winning_trades;
    result.losing_trades = report.losing_trades;
    result.max_drawdown_recovery_bars = report.max_drawdown_recovery_bars;

    const auto detailed = PerformanceAnalyzer::analyze(bt, req.trading_days_per_year);    result.num_drawdown_periods = detailed.drawdowns.size();
    result.num_yearly_periods = detailed.yearly_returns.size();
    result.num_monthly_periods = detailed.monthly_returns.size();

    result.result_hash = result.compute_result_hash();
    return result;
  }
};

std::shared_ptr<IBridgeBackend> create_backend() {
  return std::make_shared<BridgeBackend>();
}

} // namespace quant::bridge
