#include <nanobind/nanobind.h>

#include "quant/market/anti_trap.h"

namespace nb = nanobind;
using namespace nanobind::literals;
using quant::microstructure::AntiTrapInput;
using quant::microstructure::AntiTrapResult;

NB_MODULE(qros_anti_trap, m) {
  m.doc() = "Evidence-based QROS anti-trap signal quality gate; no order execution.";

  nb::class_<AntiTrapInput>(m, "AntiTrapInput")
      .def(nb::init<>())
      .def_rw("open", &AntiTrapInput::open)
      .def_rw("high", &AntiTrapInput::high)
      .def_rw("low", &AntiTrapInput::low)
      .def_rw("close", &AntiTrapInput::close)
      .def_rw("prior_range_high", &AntiTrapInput::prior_range_high)
      .def_rw("prior_range_low", &AntiTrapInput::prior_range_low)
      .def_rw("atr", &AntiTrapInput::atr)
      .def_rw("spread_price", &AntiTrapInput::spread_price)
      .def_rw("max_spread_price", &AntiTrapInput::max_spread_price)
      .def_rw("estimated_slippage_price", &AntiTrapInput::estimated_slippage_price)
      .def_rw("max_slippage_price", &AntiTrapInput::max_slippage_price)
      .def_rw("signal_age_ns", &AntiTrapInput::signal_age_ns)
      .def_rw("max_signal_age_ns", &AntiTrapInput::max_signal_age_ns)
      .def_rw("max_impulse_atr", &AntiTrapInput::max_impulse_atr);

  nb::class_<AntiTrapResult>(m, "AntiTrapResult")
      .def_ro("allow_long", &AntiTrapResult::allow_long)
      .def_ro("allow_short", &AntiTrapResult::allow_short)
      .def_ro("reason_mask", &AntiTrapResult::reason_mask)
      .def_ro("impulse_atr", &AntiTrapResult::impulse_atr)
      .def_ro("upper_wick_fraction", &AntiTrapResult::upper_wick_fraction)
      .def_ro("lower_wick_fraction", &AntiTrapResult::lower_wick_fraction)
      .def_ro("upward_sweep_atr", &AntiTrapResult::upward_sweep_atr)
      .def_ro("downward_sweep_atr", &AntiTrapResult::downward_sweep_atr);

  m.def("evaluate_anti_trap", &quant::microstructure::evaluate_anti_trap, "input"_a);
}
