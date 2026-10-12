#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>

#include "quant/market/latency.h"

#include <cstdint>
#include <stdexcept>

namespace nb = nanobind;
using namespace nanobind::literals;

NB_MODULE(qros_latency, m) {
  m.doc() = "Deterministic QROS latency decomposition and expected slippage model";

  nb::class_<quant::microstructure::LatencyBreakdown>(m, "LatencyBreakdown")
      .def(nb::init<>())
      .def_rw("network_ns", &quant::microstructure::LatencyBreakdown::network_ns)
      .def_rw("serialization_ns", &quant::microstructure::LatencyBreakdown::serialization_ns)
      .def_rw("queue_ns", &quant::microstructure::LatencyBreakdown::queue_ns)
      .def_rw("processing_ns", &quant::microstructure::LatencyBreakdown::processing_ns);

  nb::class_<quant::microstructure::ExecutionPenalty>(m, "ExecutionPenalty")
      .def_ro("elapsed_seconds", &quant::microstructure::ExecutionPenalty::elapsed_seconds)
      .def_ro("expected_drift_price", &quant::microstructure::ExecutionPenalty::expected_drift_price)
      .def_ro("expected_diffusion_abs_price", &quant::microstructure::ExecutionPenalty::expected_diffusion_abs_price)
      .def_ro("expected_market_impact_price", &quant::microstructure::ExecutionPenalty::expected_market_impact_price)
      .def_ro("expected_total_price", &quant::microstructure::ExecutionPenalty::expected_total_price)
      .def_ro("order_to_liquidity_ratio", &quant::microstructure::ExecutionPenalty::order_to_liquidity_ratio);

  m.def("total_latency_ns", &quant::microstructure::total_latency_ns, "latency"_a);
  m.def("observed_feed_latency_ns", &quant::microstructure::observed_feed_latency_ns,
        "event_time_ns"_a, "ingest_time_ns"_a);
  m.def("project_price_after_latency", &quant::microstructure::project_price_after_latency,
        "reference_price"_a, "drift_price_per_second"_a, "latency_ns"_a,
        "epsilon_price"_a = 0.0);
  m.def("estimate_execution_penalty", &quant::microstructure::estimate_execution_penalty,
        "latency_ns"_a, "volatility_price_per_sqrt_second"_a,
        "drift_price_per_second"_a, "order_size"_a, "available_liquidity"_a,
        "impact_coefficient"_a);
}
