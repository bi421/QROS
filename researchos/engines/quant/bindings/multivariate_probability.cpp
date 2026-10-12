#include <nanobind/nanobind.h>
#include "quant/market/multivariate_probability.h"
namespace nb=nanobind; using namespace nanobind::literals;
NB_MODULE(qros_probability,m) {
  m.doc()="QROS multivariate probability score and calibrated research gate";
  nb::class_<quant::microstructure::MultivariateProbabilityInput>(m,"Input").def(nb::init<>())
    .def_rw("base_probability",&quant::microstructure::MultivariateProbabilityInput::base_probability)
    .def_rw("latency_ms",&quant::microstructure::MultivariateProbabilityInput::latency_ms)
    .def_rw("vxy",&quant::microstructure::MultivariateProbabilityInput::vxy)
    .def_rw("dxy",&quant::microstructure::MultivariateProbabilityInput::dxy)
    .def_rw("dxy_baseline",&quant::microstructure::MultivariateProbabilityInput::dxy_baseline)
    .def_rw("alpha_per_ms",&quant::microstructure::MultivariateProbabilityInput::alpha_per_ms)
    .def_rw("beta_per_vxy_unit",&quant::microstructure::MultivariateProbabilityInput::beta_per_vxy_unit)
    .def_rw("gamma_per_dxy_point",&quant::microstructure::MultivariateProbabilityInput::gamma_per_dxy_point)
    .def_rw("gate_threshold",&quant::microstructure::MultivariateProbabilityInput::gate_threshold)
    .def_rw("calibration_verified",&quant::microstructure::MultivariateProbabilityInput::calibration_verified);
  nb::class_<quant::microstructure::MultivariateProbabilityResult>(m,"Result")
    .def_ro("latency_penalty",&quant::microstructure::MultivariateProbabilityResult::latency_penalty)
    .def_ro("volatility_penalty",&quant::microstructure::MultivariateProbabilityResult::volatility_penalty)
    .def_ro("dollar_deviation_penalty",&quant::microstructure::MultivariateProbabilityResult::dollar_deviation_penalty)
    .def_ro("estimated_success_probability",&quant::microstructure::MultivariateProbabilityResult::estimated_success_probability)
    .def_ro("calibration_verified",&quant::microstructure::MultivariateProbabilityResult::calibration_verified)
    .def_ro("research_gate_pass",&quant::microstructure::MultivariateProbabilityResult::research_gate_pass);
  m.def("evaluate",&quant::microstructure::evaluate_multivariate_probability,"input"_a);
}
