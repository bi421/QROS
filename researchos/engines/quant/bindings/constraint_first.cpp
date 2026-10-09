#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/vector.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <unordered_map>
#include <vector>

namespace nb = nanobind;

using ReadOnlyF64 = nb::ndarray<nb::numpy, const double, nb::ndim<1>, nb::c_contig>;
using ReadOnlyI32 = nb::ndarray<nb::numpy, const std::int32_t, nb::ndim<1>, nb::c_contig>;

namespace {

struct HorizonReturns {
  std::vector<double> bps;
};

double nan_value() { return std::numeric_limits<double>::quiet_NaN(); }

}  // namespace

NB_MODULE(qros_constraint_engine, m) {
  m.doc() = "Constraint-first empirical horizon-probability engine (C++20).";

  m.def(
      "evaluate_candidates",
      [](ReadOnlyF64 closes, ReadOnlyF64 target_bps, ReadOnlyI32 horizons,
         ReadOnlyI32 directions, std::size_t max_unique_horizons = 64) {
        const std::size_t n = closes.shape(0);
        const std::size_t count = target_bps.shape(0);
        if (n < 3) throw std::invalid_argument("closes must contain at least 3 prices");
        if (horizons.shape(0) != count || directions.shape(0) != count)
          throw std::invalid_argument("candidate arrays must have equal lengths");
        if (max_unique_horizons == 0)
          throw std::invalid_argument("max_unique_horizons must be positive");

        for (std::size_t i = 0; i < n; ++i) {
          if (!std::isfinite(closes.data()[i]) || closes.data()[i] <= 0.0)
            throw std::invalid_argument("closes must be finite and strictly positive");
        }

        std::vector<std::int32_t> unique_horizons;
        unique_horizons.reserve(std::min(count, max_unique_horizons));
        for (std::size_t i = 0; i < count; ++i) {
          const auto h = horizons.data()[i];
          const double target = target_bps.data()[i];
          const auto direction = directions.data()[i];
          if (h <= 0 || static_cast<std::size_t>(h) >= n - 1)
            throw std::invalid_argument("candidate horizon must be in [1, candle_count - 2]");
          if (!std::isfinite(target) || target <= 0.0)
            throw std::invalid_argument("target_bps must be finite and positive");
          if (direction != 1 && direction != -1)
            throw std::invalid_argument("direction must be +1 (long) or -1 (short)");
          if (std::find(unique_horizons.begin(), unique_horizons.end(), h) == unique_horizons.end()) {
            unique_horizons.push_back(h);
            if (unique_horizons.size() > max_unique_horizons)
              throw std::invalid_argument("candidate set exceeds max_unique_horizons; split into bounded batches");
          }
        }

        std::unordered_map<std::int32_t, HorizonReturns> cache;
        cache.reserve(unique_horizons.size());
        {
          nb::gil_scoped_release release;
          for (const auto h : unique_horizons) {
            HorizonReturns data;
            data.bps.reserve(n - static_cast<std::size_t>(h));
            for (std::size_t i = 0; i + static_cast<std::size_t>(h) < n; ++i) {
              const double r = (closes.data()[i + static_cast<std::size_t>(h)] /
                                closes.data()[i] - 1.0) * 10000.0;
              data.bps.push_back(r);
            }
            std::sort(data.bps.begin(), data.bps.end());
            cache.emplace(h, std::move(data));
          }
        }

        std::vector<double> probabilities(count, nan_value());
        std::vector<std::int64_t> wins(count, 0);
        std::vector<std::int64_t> samples(count, 0);
        for (std::size_t i = 0; i < count; ++i) {
          const auto& values = cache.at(horizons.data()[i]).bps;
          const double target = target_bps.data()[i];
          const auto split = directions.data()[i] == 1
              ? std::lower_bound(values.begin(), values.end(), target)
              : std::upper_bound(values.begin(), values.end(), -target);
          const auto win_count = directions.data()[i] == 1
              ? static_cast<std::int64_t>(values.end() - split)
              : static_cast<std::int64_t>(split - values.begin());
          wins[i] = win_count;
          samples[i] = static_cast<std::int64_t>(values.size());
          probabilities[i] = values.empty() ? nan_value()
              : static_cast<double>(win_count) / static_cast<double>(values.size());
        }

        nb::dict out;
        out["probability"] = std::move(probabilities);
        out["wins"] = std::move(wins);
        out["sample_size"] = std::move(samples);
        out["unique_horizons"] = unique_horizons.size();
        out["candle_count"] = n;
        out["probability_definition"] =
            "historical fraction of forward close-to-close returns meeting target_bps; before costs; overlapping samples";
        out["warning"] =
            "Exploratory empirical rate only: overlapping outcomes are dependent; validate on a chronological holdout and account for spread, slippage, and multiple testing.";
        return out;
      },
      nb::arg("closes").noconvert(),
      nb::arg("target_bps").noconvert(),
      nb::arg("horizons").noconvert(),
      nb::arg("directions").noconvert(),
      nb::arg("max_unique_horizons") = 64,
      "Evaluate bounded candidate hypotheses against one immutable close-price snapshot. Inputs must be contiguous NumPy arrays; closes are read without copying.");
}
