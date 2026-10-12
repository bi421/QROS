#pragma once
#include <cstdint>
#include <vector>

namespace quant::market_state_4d {

// A point-in-time sample. Latency is derived from both clocks; callers must
// not supply a fabricated latency field. Timestamps are UTC epoch nanoseconds.
struct DataPoint4D {
  double price{0.0};
  double volume{0.0};
  std::int64_t event_time_ns{0};
  std::int64_t ingest_time_ns{0};
  double latency_ms{0.0};
};

struct DataPoint4DView {
  const double* price;
  const double* volume;
  const std::int64_t* event_time_ns;
  const std::int64_t* ingest_time_ns;
  std::uint64_t count;
};

// Validates every input and derives latency = ingest_time - event_time.
// Negative latency beyond tolerated clock skew is rejected. Small negative
// values are retained as clock-skew evidence, not silently clamped.
std::vector<DataPoint4D> build_points(DataPoint4DView input,
                                     double allowed_clock_skew_ms = 1.0);

}  // namespace quant::market_state_4d
