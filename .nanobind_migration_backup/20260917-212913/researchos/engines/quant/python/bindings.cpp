#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "backtest.h"

namespace py = pybind11;

PYBIND11_MODULE(cpp_quant, m) {
    m.def("run_ml_backtest_cpp", &run_ml_backtest_cpp,
          "Fast ML backtest in C++",
          py::arg("prices"), py::arg("probabilities"),
          py::arg("threshold"), py::arg("initial_capital") = 100000.0,
          py::arg("commission") = 0.001, py::arg("slippage") = 0.0005);
}
