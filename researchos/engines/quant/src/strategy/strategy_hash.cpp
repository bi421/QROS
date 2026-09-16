#include <cmath>
#include "strategy_internal.h"

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <iomanip>
#include <sstream>

namespace quant {
namespace strategy {
namespace detail {

// ── SHA-256 (FIPS 180-4) ────────────────────────────────────────────────────

namespace {

constexpr uint32_t kK[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

inline uint32_t rotr(uint32_t x, uint32_t n) {
  return (x >> n) | (x << (32 - n));
}

void sha256_compress(uint32_t h[8], const uint8_t* chunk) {
  uint32_t w[64];
  for (int i = 0; i < 16; ++i) {
    w[i] = (static_cast<uint32_t>(chunk[i * 4]) << 24) |
           (static_cast<uint32_t>(chunk[i * 4 + 1]) << 16) |
           (static_cast<uint32_t>(chunk[i * 4 + 2]) << 8) |
           (static_cast<uint32_t>(chunk[i * 4 + 3]));
  }
  for (int i = 16; i < 64; ++i) {
    uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
    uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }

  uint32_t a = h[0], b = h[1], c = h[2], d = h[3];
  uint32_t e = h[4], f = h[5], g = h[6], hh = h[7];

  for (int i = 0; i < 64; ++i) {
    uint32_t s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
    uint32_t ch = (e & f) ^ (~e & g);
    uint32_t t1 = hh + s1 + ch + kK[i] + w[i];
    uint32_t s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
    uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
    uint32_t t2 = s0 + maj;
    hh = g; g = f; f = e; e = d + t1;
    d = c; c = b; b = a; a = t1 + t2;
  }

  h[0] += a; h[1] += b; h[2] += c; h[3] += d;
  h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
}

} // namespace

std::string sha256_hex(const std::string& input) {
  uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                   0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};

  const size_t len = input.size();
  const uint64_t bit_len = static_cast<uint64_t>(len) * 8;

  size_t chunks = (len + 1 + 8 + 63) / 64;
  std::vector<uint8_t> padded(chunks * 64, 0);
  std::memcpy(padded.data(), input.data(), len);
  padded[len] = 0x80;
  for (int i = 0; i < 8; ++i) {
    padded[padded.size() - 1 - i] =
        static_cast<uint8_t>((bit_len >> (i * 8)) & 0xFF);
  }

  for (size_t i = 0; i < chunks; ++i) {
    sha256_compress(h, padded.data() + i * 64);
  }

  std::array<char, 65> hex{};
  for (int i = 0; i < 8; ++i) {
    std::snprintf(hex.data() + i * 8, 9, "%08x", h[i]);
  }
  return std::string(hex.data(), 64);
}

// ── Time helpers ────────────────────────────────────────────────────────────

namespace {

void to_utc_tm(const time_t t, std::tm& out) {
#ifdef _WIN32
  gmtime_s(&out, &t);
#else
  gmtime_r(&t, &out);
#endif
}

int weekday_of_tm(const std::tm& tm) { return tm.tm_wday; }

} // namespace

UtcParts utc_parts(TimePoint tp) {
  std::tm tm{};
  to_utc_tm(std::chrono::system_clock::to_time_t(tp), tm);
  UtcParts p;
  p.year = tm.tm_year + 1900;
  p.month = tm.tm_mon + 1;
  p.day = tm.tm_mday;
  p.hour = tm.tm_hour;
  p.weekday = tm.tm_wday;
  p.day_key = static_cast<int64_t>(p.year) * 10000 +
              static_cast<int64_t>(p.month) * 100 + p.day;
  return p;
}

std::string iso8601(TimePoint tp) {
  std::tm tm{};
  to_utc_tm(std::chrono::system_clock::to_time_t(tp), tm);
  char buf[32];
  std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d",
                tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday, tm.tm_hour,
                tm.tm_min, tm.tm_sec);
  return std::string(buf);
}

// ── Canonical primitives ────────────────────────────────────────────────────

std::string canonical_double(double v) {
  if (std::isnan(v)) return "null";
  if (std::isinf(v)) return v > 0 ? "1e999" : "-1e999";
  char buf[64];
  std::snprintf(buf, sizeof(buf), "%.10f", v);
  return buf;
}

std::string canonical_int(int64_t v) { return std::to_string(v); }

std::string canonical_bool(bool b) { return b ? "true" : "false"; }

std::string json_escape(const std::string& s) {
  std::string out;
  out.reserve(s.size() + 2);
  out.push_back('"');
  for (char c : s) {
    switch (c) {
      case '"': out += "\\\""; break;
      case '\\': out += "\\\\"; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default:
        if (static_cast<unsigned char>(c) < 0x20) {
          char buf[8];
          std::snprintf(buf, sizeof(buf), "\\u%04x", c);
          out += buf;
        } else {
          out.push_back(c);
        }
    }
  }
  out.push_back('"');
  return out;
}

std::string canonical_str(const std::string& s) { return json_escape(s); }

std::string canonical_double_array(const std::vector<double>& a) {
  std::string out = "[";
  for (size_t i = 0; i < a.size(); ++i) {
    if (i) out += ",";
    out += canonical_double(a[i]);
  }
  out += "]";
  return out;
}

std::string canonical_int_array(const std::vector<int64_t>& a) {
  std::string out = "[";
  for (size_t i = 0; i < a.size(); ++i) {
    if (i) out += ",";
    out += canonical_int(a[i]);
  }
  out += "]";
  return out;
}

std::string canonical_object(std::initializer_list<KV> kvs) {
  std::vector<KV> sorted(kvs);
  std::sort(sorted.begin(), sorted.end(),
            [](const KV& a, const KV& b) { return a.first < b.first; });
  std::string out = "{";
  for (size_t i = 0; i < sorted.size(); ++i) {
    if (i) out += ",";
    out += json_escape(sorted[i].first);
    out += ":";
    out += sorted[i].second;
  }
  out += "}";
  return out;
}

std::string canonical_object(const std::vector<KV>& kvs) {
  auto sorted = kvs;
  std::sort(sorted.begin(), sorted.end(),
            [](const KV& a, const KV& b) { return a.first < b.first; });
  std::string out = "{";
  for (size_t i = 0; i < sorted.size(); ++i) {
    if (i) out += ",";
    out += json_escape(sorted[i].first);
    out += ":";
    out += sorted[i].second;
  }
  out += "}";
  return out;
}

std::string canonical_array(std::initializer_list<std::string> items) {
  std::string out = "[";
  size_t i = 0;
  for (const auto& s : items) {
    if (i++) out += ",";
    out += s;
  }
  out += "]";
  return out;
}

std::string canonical_array(const std::vector<std::string>& items) {
  std::string out = "[";
  for (size_t i = 0; i < items.size(); ++i) {
    if (i) out += ",";
    out += items[i];
  }
  out += "]";
  return out;
}

} // namespace detail
} // namespace strategy
} // namespace quant
