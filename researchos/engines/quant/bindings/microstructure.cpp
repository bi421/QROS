#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/tuple.h>

#include "quant/market/microstructure.h"

#include <cstdint>
#include <memory>
#include <vector>

namespace nb = nanobind;
using ReadOnlyF64 = nb::ndarray<nb::numpy, const double, nb::ndim<1>, nb::c_contig>;

namespace {

template <typename T>
nb::ndarray<nb::numpy, T> owned_array(std::vector<T> values) {
  auto owner = std::make_shared<std::vector<T>>(std::move(values));
  const std::size_t shape[] = {owner->size()};
  auto* holder = new std::shared_ptr<std::vector<T>>(owner);
  nb::capsule capsule(holder, [](void* ptr) noexcept {
    delete static_cast<std::shared_ptr<std::vector<T>>*>(ptr);
  });
  return nb::ndarray<nb::numpy, T>(owner->data(), 1, shape, capsule);
}

}  // namespace

NB_MODULE(qros_microstructure, m) {
  m.doc() = "QROS deterministic C++20 microstructure kernels; contiguous NumPy inputs are borrowed without copying.";

  m.def(
      "order_flow_imbalance",
      [](ReadOnlyF64 bid_price, ReadOnlyF64 bid_size,
         ReadOnlyF64 ask_price, ReadOnlyF64 ask_size) {
        const auto n = bid_price.shape(0);
        if (bid_size.shape(0) != n || ask_price.shape(0) != n ||
            ask_size.shape(0) != n) {
          throw std::invalid_argument("all book arrays must have identical lengths");
        }
        std::vector<double> result;
        {
          nb::gil_scoped_release release;
          result = quant::microstructure::order_flow_imbalance(
              bid_price.data(), bid_size.data(), ask_price.data(), ask_size.data(), n);
        }
        return owned_array(std::move(result));
      },
      "bid_price"_a, "bid_size"_a, "ask_price"_a, "ask_size"_a);

  m.def(
      "detect_liquidity_sweeps",
      [](ReadOnlyF64 high, ReadOnlyF64 low, ReadOnlyF64 close, double pool_price) {
        const auto n = high.shape(0);
        if (low.shape(0) != n || close.shape(0) != n) {
          throw std::invalid_argument("high, low and close arrays must have identical lengths");
        }
        std::vector<quant::microstructure::SweepResult> result;
        {
          nb::gil_scoped_release release;
          result = quant::microstructure::detect_liquidity_sweeps(
              high.data(), low.data(), close.data(), n, pool_price);
        }
        std::vector<std::uint8_t> above;
        std::vector<std::uint8_t> below;
        above.reserve(result.size());
        below.reserve(result.size());
        for (const auto& item : result) {
          above.push_back(item.swept_above);
          below.push_back(item.swept_below);
        }
        return nb::make_tuple(owned_array(std::move(above)), owned_array(std::move(below)));
      },
      "high"_a, "low"_a, "close"_a, "pool_price"_a);

  m.def(
      "volume_profile_summary",
      [](ReadOnlyF64 prices, ReadOnlyF64 volumes, double tick_size,
         double value_area_fraction) {
        if (volumes.shape(0) != prices.shape(0)) {
          throw std::invalid_argument("prices and volumes must have identical lengths");
        }
        quant::microstructure::VolumeProfileSummary result;
        {
          nb::gil_scoped_release release;
          result = quant::microstructure::volume_profile_summary(
              prices.data(), volumes.data(), prices.shape(0), tick_size,
              value_area_fraction);
        }
        nb::dict out;
        out["poc_price"] = result.poc_price;
        out["value_area_low"] = result.value_area_low;
        out["value_area_high"] = result.value_area_high;
        out["total_volume"] = result.total_volume;
        out["occupied_bins"] = result.occupied_bins;
        return out;
      },
      "prices"_a, "volumes"_a, "tick_size"_a, "value_area_fraction"_a = 0.70);
}
