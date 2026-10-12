#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include "quant/biberion/research_kernel.h"

namespace nb = nanobind;
using namespace nanobind::literals;
using namespace quant::biberion;

NB_MODULE(qros_biberion, m) {
    m.doc() = "QROS Biberion-inspired deterministic research kernels; no order execution";

    nb::class_<VolumeSurge>(m, "VolumeSurge")
        .def(nb::init<std::size_t, double>(), "window"_a = 50, "sigma_multiplier"_a = 2.0)
        .def("observe", &VolumeSurge::observe, "volume"_a)
        .def_prop_ro("threshold", &VolumeSurge::threshold)
        .def_prop_ro("samples", &VolumeSurge::samples);

    nb::class_<Signal>(m, "Signal")
        .def_ro("direction", &Signal::direction)
        .def_ro("approved", &Signal::approved)
        .def_ro("reason", &Signal::reason);

    m.def("evaluate_cross", &evaluate_cross,
          "closes"_a, "benchmark_closes"_a, "fast_window"_a = 5,
          "slow_window"_a = 25, "volume_surge"_a = false,
          "sideline_lockdown"_a = false);

    nb::class_<BasketLimits>(m, "BasketLimits")
        .def(nb::init<>())
        .def_rw("equity", &BasketLimits::equity)
        .def_rw("max_assets", &BasketLimits::max_assets)
        .def_rw("max_basket_fraction", &BasketLimits::max_basket_fraction)
        .def_rw("max_asset_fraction", &BasketLimits::max_asset_fraction)
        .def_rw("max_asset_risk_fraction", &BasketLimits::max_asset_risk_fraction)
        .def_rw("max_basket_risk_fraction", &BasketLimits::max_basket_risk_fraction);

    nb::class_<BasketProposal>(m, "BasketProposal")
        .def(nb::init<>())
        .def_rw("symbol", &BasketProposal::symbol)
        .def_rw("entry", &BasketProposal::entry)
        .def_rw("stop", &BasketProposal::stop)
        .def_rw("requested_notional", &BasketProposal::requested_notional);

    nb::class_<BasketDecision>(m, "BasketDecision")
        .def_ro("approved", &BasketDecision::approved)
        .def_ro("total_notional", &BasketDecision::total_notional)
        .def_ro("planned_loss", &BasketDecision::planned_loss)
        .def_ro("reason", &BasketDecision::reason);

    m.def("approve_cash_basket", &approve_cash_basket,
          "limits"_a, "proposals"_a);
}
