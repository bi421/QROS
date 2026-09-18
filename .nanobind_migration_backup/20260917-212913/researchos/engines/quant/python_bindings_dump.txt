#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "quant_engine.h"
#include "statistics.h"

namespace py = pybind11;

PYBIND11_MODULE(cpp_quant_core, m) {
    m.doc() = "C++ Quant Engine for ResearchOS with Statistics";

    // ---------- Candle ----------
    py::class_<cpp_quant::Candle>(m, "Candle")
        .def_readwrite("timestamp", &cpp_quant::Candle::timestamp)
        .def_readwrite("open", &cpp_quant::Candle::open)
        .def_readwrite("high", &cpp_quant::Candle::high)
        .def_readwrite("low", &cpp_quant::Candle::low)
        .def_readwrite("close", &cpp_quant::Candle::close)
        .def_readwrite("volume", &cpp_quant::Candle::volume);

    // ---------- Trade ----------
    py::class_<cpp_quant::Trade>(m, "Trade")
        .def_readwrite("entry_time", &cpp_quant::Trade::entry_time)
        .def_readwrite("exit_time", &cpp_quant::Trade::exit_time)
        .def_readwrite("entry_price", &cpp_quant::Trade::entry_price)
        .def_readwrite("exit_price", &cpp_quant::Trade::exit_price)
        .def_readwrite("pnl", &cpp_quant::Trade::pnl)
        .def_readwrite("is_win", &cpp_quant::Trade::is_win);

    // ---------- BacktestResult ----------
    py::class_<cpp_quant::BacktestResult>(m, "BacktestResult")
        .def_readwrite("num_trades", &cpp_quant::BacktestResult::num_trades)
        .def_readwrite("winrate", &cpp_quant::BacktestResult::winrate)
        .def_readwrite("total_return", &cpp_quant::BacktestResult::total_return)
        .def_readwrite("sharpe_ratio", &cpp_quant::BacktestResult::sharpe_ratio)
        .def_readwrite("max_drawdown", &cpp_quant::BacktestResult::max_drawdown)
        .def_readwrite("avg_win", &cpp_quant::BacktestResult::avg_win)
        .def_readwrite("avg_loss", &cpp_quant::BacktestResult::avg_loss)
        .def_readwrite("profit_factor", &cpp_quant::BacktestResult::profit_factor)
        .def_readwrite("trades", &cpp_quant::BacktestResult::trades);

    // ---------- QuantEngine ----------
    py::class_<cpp_quant::QuantEngine>(m, "QuantEngine")
        .def(py::init<>())
        .def("load_data", &cpp_quant::QuantEngine::loadData)
        .def("load_data_from_vectors", &cpp_quant::QuantEngine::loadDataFromVectors)
        .def("set_timeframe", &cpp_quant::QuantEngine::setTimeframe)
        .def("get_data_size", &cpp_quant::QuantEngine::getDataSize)
        .def("get_data_info", &cpp_quant::QuantEngine::getDataInfo)
        .def("run_sma", &cpp_quant::QuantEngine::runSMA)
        .def("run_rsi", &cpp_quant::QuantEngine::runRSI)
        .def("run_macd", &cpp_quant::QuantEngine::runMACD)
        .def("run_all_strategies", &cpp_quant::QuantEngine::runAllStrategies)
        .def("monte_carlo_pvalue", &cpp_quant::QuantEngine::monteCarloPValue)
        .def("optimize_sma", &cpp_quant::QuantEngine::optimizeSMA);

    // ---------- Statistics (????) ----------
    m.def("mean", &cpp_quant::Statistics::mean, "Calculate mean of a list");
    m.def("stddev", &cpp_quant::Statistics::stddev, "Calculate standard deviation (population)");
    m.def("correlation", &cpp_quant::Statistics::correlation, "Calculate Pearson correlation");
    m.def("quantile", &cpp_quant::Statistics::quantile, "Calculate quantile (0..1)");
    m.def("bootstrap_ci", &cpp_quant::Statistics::bootstrap_ci,
          "Bootstrap CI for mean: (data, iterations=1000, ci=0.95) -> (low, high)");
    m.def("bootstrap_winrate_ci", &cpp_quant::Statistics::bootstrap_winrate_ci,
          "Bootstrap CI for winrate: (pnl_list, iterations=1000, ci=0.95) -> (low, high)");
}
