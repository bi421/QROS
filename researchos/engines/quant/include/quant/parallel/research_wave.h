#pragma once

#include <cstddef>
#include <vector>

namespace quant::parallel {

struct ResearchWaveResult {
  double mean{0.0};
  double variance{0.0};
  double standard_deviation{0.0};
  double linear_slope{0.0};
  double positive_rate{0.0};
  std::size_t sample_size{0};
};

// Runs independent deterministic measurements over one immutable snapshot.
// The measurements are intentionally descriptive; they are NOT probabilities.
ResearchWaveResult run_research_wave(const std::vector<double>& values);

}  // namespace quant::parallel
