// pybind11 bindings exposing the C++ Quant Engine to Python.
//
// Two surfaces are provided:
//   1. `Backend`       — the stable Python/C++ integration contract
//                        (mirrors python/cpp_quant_engine/backend.py).
//   2. `CppQuantBackend` — legacy QuantComputationInterface shim for
//                        backward compatibility with ResearchOS callers.
//
// The bridge operates on plain dicts of primitives (Python BaseObjects) that
// are losslessly converted to/from the value models in
// python/bridge_models.h. Hashes (input_hash/result_hash) are computed in C++
// with a canonical serialization that python/cpp_quant_engine/models.py
// reproduces byte-for-byte.

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
#include <pybind11/pytypes.h>

#include "bridge_interface.h"
#include "bridge_models.h"
#include "bridge_validation.h"
#include "quant/backtest/serialization.h"
#include "quant/core/engine.h"
#include "quant/statistics/regression.h"
#include "quant/statistics/rolling.h"

#include "quant_engine.hpp"

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace py = pybind11;
namespace bridge = quant::bridge;
namespace qe = quant_engine;

using bridge::BacktestRequest;
using bridge::CandleModel;
using bridge::MarketDataRequest;
using bridge::PerformanceRequest;
using bridge::RiskRequest;
using bridge::SimulationRequest;
using bridge::StatisticsRequest;

// ── dict <-> model conversion helpers ───────────────────────────────────────

namespace {

std::string get_str(const py::dict& d, const char* key, const char* def = "") {
  if (d.contains(key) && !d[key].is_none()) return py::cast<std::string>(d[key]);
  return def;
}

double get_double(const py::dict& d, const char* key, double def = 0.0) {
  if (d.contains(key) && !d[key].is_none()) return py::cast<double>(d[key]);
  return def;
}

int get_int(const py::dict& d, const char* key, int def = 0) {
  if (d.contains(key) && !d[key].is_none()) return py::cast<int>(d[key]);
  return def;
}

bool get_bool(const py::dict& d, const char* key, bool def = false) {
  if (d.contains(key) && !d[key].is_none()) return py::cast<bool>(d[key]);
  return def;
}

std::vector<double> get_double_list(const py::dict& d, const char* key) {
  if (d.contains(key)) {
    if (d[key].is_none())
      throw bridge::BridgeError(bridge::BridgeErrorCode::InvalidType,
                                "expected a list for '" + std::string(key) + "', got None");
    return py::cast<std::vector<double>>(d[key]);
  }
  return {};
}

CandleModel candle_from_dict(const py::dict& c) {
  CandleModel out;
  out.timestamp = get_str(c, "timestamp");
  out.open = get_double(c, "open");
  out.high = get_double(c, "high");
  out.low = get_double(c, "low");
  out.close = get_double(c, "close");
  out.volume = get_double(c, "volume");
  out.timeframe = get_str(c, "timeframe", "M1");
  return out;
}

std::vector<CandleModel> get_candle_list(const py::dict& d, const char* key) {
  std::vector<CandleModel> out;
  if (!d.contains(key)) return out;
  if (d[key].is_none())
    throw bridge::BridgeError(bridge::BridgeErrorCode::InvalidType,
                              "expected a list for '" + std::string(key) + "', got None");
  const auto list = py::cast<py::list>(d[key]);
  out.reserve(list.size());
  for (const auto& item : list) out.push_back(candle_from_dict(py::cast<py::dict>(item)));
  return out;
}

py::dict candle_to_dict(const CandleModel& c) {
  py::dict out;
  out["timestamp"] = c.timestamp;
  out["open"] = c.open;
  out["high"] = c.high;
  out["low"] = c.low;
  out["close"] = c.close;
  out["volume"] = c.volume;
  out["timeframe"] = c.timeframe;
  return out;
}

py::dict meta_to_dict(const bridge::BridgeMeta& m) {
  py::dict out;
  out["engine_name"] = m.engine_name;
  out["engine_version"] = m.engine_version;
  out["bridge_version"] = m.bridge_version;
  out["protocol_version"] = m.protocol_version;
  out["calculation_version"] = m.calculation_version;
  return out;
}

py::dict market_data_result_to_dict(const bridge::MarketDataResult& r) {
  py::dict out;
  out["symbol"] = r.symbol;
  out["timeframe"] = r.timeframe;
  out["size"] = r.size;
  out["first_timestamp"] = r.first_timestamp;
  out["last_timestamp"] = r.last_timestamp;
  out["valid"] = r.valid;
  out["validation_message"] = r.validation_message;
  out["input_hash"] = r.input_hash;
  out["result_hash"] = r.result_hash;
  out["calculation_version"] = r.calculation_version;
  out["engine_version"] = r.engine_version;
  out["bridge_version"] = r.bridge_version;
  return out;
}

py::dict statistics_result_to_dict(const bridge::StatisticsResult& r) {
  py::dict out;
  out["count"] = r.count;
  out["sum"] = r.sum;
  out["mean"] = r.mean;
  out["variance"] = r.variance;
  out["stddev"] = r.stddev;
  out["skewness"] = r.skewness;
  out["kurtosis"] = r.kurtosis;
  out["min"] = r.min;
  out["max"] = r.max;
  out["q1"] = r.q1;
  out["median"] = r.median;
  out["q3"] = r.q3;
  out["iqr"] = r.iqr;
  out["input_hash"] = r.input_hash;
  out["result_hash"] = r.result_hash;
  out["calculation_version"] = r.calculation_version;
  out["engine_version"] = r.engine_version;
  out["bridge_version"] = r.bridge_version;
  return out;
}

py::dict risk_result_to_dict(const bridge::RiskResult& r) {
  py::dict out;
  out["var_95"] = r.var_95;
  out["var_99"] = r.var_99;
  out["cvar_95"] = r.cvar_95;
  out["cvar_99"] = r.cvar_99;
  out["max_drawdown_pct"] = r.max_drawdown_pct;
  out["peak_index"] = r.peak_index;
  out["trough_index"] = r.trough_index;
  out["recovery_index"] = r.recovery_index;
  out["sharpe_ratio"] = r.sharpe_ratio;
  out["sortino_ratio"] = r.sortino_ratio;
  out["input_hash"] = r.input_hash;
  out["result_hash"] = r.result_hash;
  out["calculation_version"] = r.calculation_version;
  out["engine_version"] = r.engine_version;
  out["bridge_version"] = r.bridge_version;
  return out;
}

py::dict simulation_result_to_dict(const bridge::SimulationResult& r) {
  py::dict out;
  out["simulation_id"] = r.simulation_id;
  out["dataset_reference"] = r.dataset_reference;
  out["dataset_version"] = r.dataset_version;
  out["calculation_version"] = r.calculation_version;
  out["start_time"] = r.start_time;
  out["end_time"] = r.end_time;
  out["input_hash"] = r.input_hash;
  out["result_hash"] = r.result_hash;
  out["execution_timestamp"] = r.execution_timestamp;
  out["returns"] = r.returns;
  out["equity_curve"] = r.equity_curve;
  out["metrics"] = r.metrics;
  out["statistics"] = r.statistics;
  out["performance"] = r.performance;
  out["engine_version"] = r.engine_version;
  out["bridge_version"] = r.bridge_version;
  return out;
}

py::dict backtest_result_to_dict(const bridge::BacktestResult& r) {
  py::dict out;
  out["equity_curve"] = r.equity_curve;
  out["drawdown_curve"] = r.drawdown_curve;
  out["final_equity"] = r.final_equity;
  out["total_return_pct"] = r.total_return_pct;
  out["max_drawdown_pct"] = r.max_drawdown_pct;
  out["total_bars"] = r.total_bars;
  out["num_trades"] = r.num_trades;
  out["signal_reference"] = r.signal_reference;
  out["input_hash"] = r.input_hash;
  out["result_hash"] = r.result_hash;
  out["calculation_version"] = r.calculation_version;
  out["engine_version"] = r.engine_version;
  out["bridge_version"] = r.bridge_version;
  return out;
}

py::dict performance_result_to_dict(const bridge::PerformanceResult& r) {
  py::dict out;
  out["total_return"] = r.total_return;
  out["total_return_pct"] = r.total_return_pct;
  out["annualized_return"] = r.annualized_return;
  out["annualized_volatility"] = r.annualized_volatility;
  out["sharpe_ratio"] = r.sharpe_ratio;
  out["sortino_ratio"] = r.sortino_ratio;
  out["calmar_ratio"] = r.calmar_ratio;
  out["max_drawdown_pct"] = r.max_drawdown_pct;
  out["win_rate"] = r.win_rate;
  out["profit_factor"] = r.profit_factor;
  out["downside_deviation_annualized"] = r.downside_deviation_annualized;
  out["var_95"] = r.var_95;
  out["var_99"] = r.var_99;
  out["cvar_95"] = r.cvar_95;
  out["cvar_99"] = r.cvar_99;
  out["time_in_drawdown_pct"] = r.time_in_drawdown_pct;
  out["total_trades"] = r.total_trades;
  out["winning_trades"] = r.winning_trades;
  out["losing_trades"] = r.losing_trades;
  out["num_drawdown_periods"] = r.num_drawdown_periods;
  out["num_yearly_periods"] = r.num_yearly_periods;
  out["num_monthly_periods"] = r.num_monthly_periods;
  out["max_drawdown_recovery_bars"] = r.max_drawdown_recovery_bars;
  out["input_hash"] = r.input_hash;
  out["result_hash"] = r.result_hash;
  out["calculation_version"] = r.calculation_version;
  out["engine_version"] = r.engine_version;
  out["bridge_version"] = r.bridge_version;
  return out;
}

// Python signal callable -> engine SignalFn (the bridge transports, never
// implements, trading logic).
std::optional<quant::SignalFn> make_signal_fn(const py::object& signal) {
  if (signal.is_none()) return std::nullopt;
  const py::function fn = py::cast<py::function>(signal);
  return [fn](size_t bar_index, const std::vector<quant::OHLCV>& history)
             -> quant::SignalResult {
    py::gil_scoped_acquire gil;
    py::list hist;
    for (const auto& b : history) {
      py::dict d;
      d["timestamp"] = quant::serialization::to_iso8601(b.timestamp);
      d["open"] = b.open;
      d["high"] = b.high;
      d["low"] = b.low;
      d["close"] = b.close;
      d["volume"] = b.volume;
      hist.append(d);
    }
    py::object res = fn(py::int_(bar_index), hist);
    py::dict rd = py::cast<py::dict>(res);
    quant::SignalResult sr;
    sr.direction = (py::cast<int>(rd["direction"]) == 0)
                       ? quant::TradeDirection::Buy
                       : quant::TradeDirection::Sell;
    sr.quantity = py::cast<double>(rd["quantity"]);
    if (rd.contains("stop_loss")) sr.stop_loss = py::cast<double>(rd["stop_loss"]);
    if (rd.contains("take_profit")) sr.take_profit = py::cast<double>(rd["take_profit"]);
    return sr;
  };
}

} // namespace

// ── Stable Backend (Python/C++ integration contract) ────────────────────────

class Backend {
public:
  explicit Backend(std::shared_ptr<bridge::IBridgeBackend> impl)
      : impl_(std::move(impl)) {}

  py::dict meta() const { return meta_to_dict(impl_->meta()); }

  py::str version() const { return py::str(impl_->version()); }

  py::dict market_data_load(const py::dict& request) const {
    MarketDataRequest req;
    req.symbol = get_str(request, "symbol");
    req.timeframe = get_str(request, "timeframe", "M1");
    req.candles = get_candle_list(request, "candles");
    req.calculation_version =
        get_str(request, "calculation_version", bridge::kDefaultCalculationVersion);
    return market_data_result_to_dict(impl_->market_data_load(req));
  }

  py::dict statistics_compute(const py::dict& request) const {
    StatisticsRequest req;
    req.data = get_double_list(request, "data");
    req.calculation_version =
        get_str(request, "calculation_version", bridge::kDefaultCalculationVersion);
    return statistics_result_to_dict(impl_->statistics_compute(req));
  }

  py::dict risk_compute(const py::dict& request) const {
    RiskRequest req;
    req.returns = get_double_list(request, "returns");
    req.equity_curve = get_double_list(request, "equity_curve");
    req.risk_free_rate = get_double(request, "risk_free_rate");
    req.calculation_version =
        get_str(request, "calculation_version", bridge::kDefaultCalculationVersion);
    return risk_result_to_dict(impl_->risk_compute(req));
  }

  py::dict simulation_run(const py::dict& request) const {
    SimulationRequest req;
    req.dataset_reference = get_str(request, "dataset_reference");
    req.dataset_version = get_str(request, "dataset_version", "1.0.0");
    req.calculation_version =
        get_str(request, "calculation_version", bridge::kDefaultCalculationVersion);
    req.initial_capital = get_double(request, "initial_capital", 100'000.0);
    req.risk_free_rate = get_double(request, "risk_free_rate");
    req.seed = get_int(request, "seed", 42);
    req.start_time = get_str(request, "start_time");
    req.end_time = get_str(request, "end_time");
    req.prices = get_double_list(request, "prices");
    return simulation_result_to_dict(impl_->simulation_run(req));
  }

  py::dict backtest_run(const py::dict& request,
                        const py::object& signal = py::none()) const {
    BacktestRequest req;
    req.symbol = get_str(request, "symbol");
    req.timeframe = get_str(request, "timeframe", "M1");
    req.candles = get_candle_list(request, "candles");
    req.initial_capital = get_double(request, "initial_capital", 100'000.0);
    req.commission_pct = get_double(request, "commission_pct", 0.001);
    req.slippage_pct = get_double(request, "slippage_pct", 0.0005);
    req.allow_short = get_bool(request, "allow_short", true);
    req.signal_reference = get_str(request, "signal_reference");
    req.calculation_version =
        get_str(request, "calculation_version", bridge::kDefaultCalculationVersion);

    auto fn = make_signal_fn(signal);
    const auto& sig = fn.has_value() ? *fn : bridge::BridgeSignalFn{};
    return backtest_result_to_dict(impl_->backtest_run(req, sig));
  }

  py::dict performance_analyze(const py::dict& request) const {
    PerformanceRequest req;
    req.equity_curve = get_double_list(request, "equity_curve");
    req.bars = get_candle_list(request, "bars");
    req.initial_capital = get_double(request, "initial_capital", 100'000.0);
    req.trading_days_per_year = get_double(request, "trading_days_per_year", 252.0);
    req.calculation_version =
        get_str(request, "calculation_version", bridge::kDefaultCalculationVersion);
    return performance_result_to_dict(impl_->performance_analyze(req));
  }

private:
  std::shared_ptr<bridge::IBridgeBackend> impl_;
};

// ── Legacy CppQuantBackend (backward-compatible QuantComputationInterface) ──

class CppQuantBackend {
public:
  CppQuantBackend() = default;

  std::vector<double> calculate_returns(const std::vector<double>& prices,
                                        const std::string& return_type = "percentage") {
    if (return_type == "absolute") return qe::market_data::absolute_returns(prices);
    if (return_type == "log") return qe::market_data::log_returns(prices);
    if (return_type == "percentage") return qe::market_data::percentage_returns(prices);
    throw qe::InvalidArgumentError(
        "Unrecognized return_type '" + return_type + "'. "
        "Expected 'absolute', 'percentage', or 'log'.");
  }

  double calculate_volatility(const std::vector<double>& returns,
                              const std::string& method = "standard_deviation") {
    if (returns.empty()) {
      throw qe::InsufficientDataError("Cannot compute volatility on empty dataset");
    }
    if (method == "standard_deviation") return qe::statistics::standard_deviation(returns);
    if (method == "rolling") return qe::market_data::rolling_volatility(returns);
    if (method == "change") return qe::market_data::volatility_change(returns);
    throw qe::InvalidArgumentError(
        "Unrecognized method '" + method + "'. "
        "Expected 'standard_deviation', 'rolling', or 'change'.");
  }

  std::unordered_map<std::string, double> calculate_drawdown(
      const std::vector<double>& equity_curve) {
    return qe::market_data::max_drawdown(equity_curve).to_dict();
  }

  std::unordered_map<std::string, double> calculate_statistics(
      const std::vector<double>& returns) {
    return qe::statistics::distribution_summary(returns).to_dict();
  }

  std::unordered_map<std::string, double> calculate_metrics(
      const std::vector<double>& returns, const std::vector<double>& equity_curve,
      double risk_free_rate = 0.0) {
    return qe::metrics::compute_all_metrics(returns, equity_curve, risk_free_rate);
  }

  std::unordered_map<std::string, double> calculate_performance_analytics(
      const std::vector<double>& returns) {
    std::unordered_map<std::string, double> result;
    result["win_rate"] = qe::metrics::win_rate(returns);
    result["profit_factor"] = qe::metrics::profit_factor(returns);
    result["average_return"] = qe::metrics::average_return(returns);

    double total = 0.0;
    for (double r : returns) {
      if (r > 0) total += 1.0;
    }
    result["loss_rate"] = returns.empty() ? 0.0 : 1.0 - (total / returns.size());

    double sum = 0.0;
    for (double r : returns) sum += r;
    result["total_return"] = sum;
    result["count"] = static_cast<double>(returns.size());
    return result;
  }

  std::unordered_map<std::string, py::object> run_simulation(
      const std::unordered_map<std::string, py::object>& request_dict,
      const std::vector<double>& prices) {
    qe::simulation::SimulationInput input;
    auto get_str = [&](const std::string& key, const std::string& default_val) {
      auto it = request_dict.find(key);
      if (it != request_dict.end()) return py::cast<std::string>(it->second);
      return default_val;
    };
    auto get_double = [&](const std::string& key, double default_val) {
      auto it = request_dict.find(key);
      if (it != request_dict.end()) return py::cast<double>(it->second);
      return default_val;
    };
    auto get_int = [&](const std::string& key, int default_val) {
      auto it = request_dict.find(key);
      if (it != request_dict.end()) return py::cast<int>(it->second);
      return default_val;
    };

    input.dataset_reference = get_str("dataset_reference", "");
    input.dataset_version = get_str("dataset_version", "1.0.0");
    input.calculation_version = get_str("calculation_version", "CALCULATION_V1");
    input.initial_capital = get_double("initial_capital", 100000.0);
    input.risk_free_rate = get_double("risk_free_rate", 0.0);
    input.seed = get_int("seed", 42);

    auto output = qe::simulation::run_simulation(input, prices);

    std::unordered_map<std::string, py::object> result;
    result["returns"] = py::cast(output.returns);
    result["equity_curve"] = py::cast(output.equity_curve);
    result["metrics"] = py::cast(output.metrics);
    result["statistics"] = py::cast(output.statistics);
    result["performance"] = py::cast(output.performance);
    result["input_hash"] = py::cast(output.input_hash);
    result["result_hash"] = py::cast(output.result_hash);
    return result;
  }

  std::string get_version() const { return qe::ENGINE_VERSION; }

  double mean(const std::vector<double>& data) { return qe::statistics::mean(data); }
  double std_dev(const std::vector<double>& data) {
    return qe::statistics::standard_deviation(data);
  }
  double variance(const std::vector<double>& data) { return qe::statistics::variance(data); }
  double z_score(double value, double mean, double std) {
    return qe::statistics::z_score(value, mean, std);
  }

  // ── Regression (trend form: OLS vs implicit index x = 0..n-1) ────────────
  double regression_slope(const std::vector<double>& y) {
    auto r = quant::statistics::Regression::slope(y);
    if (r.is_err())
      throw qe::InvalidArgumentError(r.error().message());
    return r.value();
  }

  double regression_intercept(const std::vector<double>& y) {
    auto r = quant::statistics::Regression::intercept(y);
    if (r.is_err())
      throw qe::InvalidArgumentError(r.error().message());
    return r.value();
  }

  // ── Regression (pairwise form on explicit (x, y) sample) ─────────────────
  double regression_correlation(const std::vector<double>& x,
                                const std::vector<double>& y) {
    auto r = quant::statistics::Regression::correlation(x, y);
    if (r.is_err())
      throw qe::InvalidArgumentError(r.error().message());
    return r.value();
  }

  double regression_r_squared(const std::vector<double>& x,
                              const std::vector<double>& y) {
    auto r = quant::statistics::Regression::r_squared(x, y);
    if (r.is_err())
      throw qe::InvalidArgumentError(r.error().message());
    return r.value();
  }

  double regression_standard_error(const std::vector<double>& x,
                                   const std::vector<double>& y) {
    auto r = quant::statistics::Regression::standard_error(x, y);
    if (r.is_err())
      throw qe::InvalidArgumentError(r.error().message());
    return r.value();
  }

  // ── Rolling statistics ────────────────────────────────────────────────────
  std::vector<double> rolling_mean(const std::vector<double>& data, size_t window) {
    auto r = quant::RollingWindow::mean(data, window);
    if (r.is_err())
      throw qe::InvalidArgumentError(r.error().message());
    return r.value();
  }

std::vector<double> rolling_volatility_series_ext(const std::vector<double>& data,
                                                     size_t window, int ddof) {
    auto r = quant::RollingWindow::volatility(data, window, ddof);
    if (r.is_err())
      throw qe::InvalidArgumentError(r.error().message());
    return r.value();
  }

  std::vector<double> rolling_variance_ext(const std::vector<double>& data,
                                            size_t window, int ddof) {
    auto r = quant::RollingWindow::variance(data, window, ddof);
    if (r.is_err())
      throw qe::InvalidArgumentError(r.error().message());
    return r.value();
  }
};

// ── Module Definition ───────────────────────────────────────────────────────

PYBIND11_MODULE(cpp_quant_backend, m) {
  m.doc() = "C++20 Quant Computation Engine for ResearchOS — stable Python/C++ integration bridge";

  // Bridge errors are raised as the typed Python exceptions defined in
  // cpp_quant_engine/exceptions.py (selected by the stable numeric code).
  py::register_exception_translator([](std::exception_ptr p) {
    try {
      if (p) std::rethrow_exception(p);
    } catch (const bridge::BridgeError& e) {
      py::object exc;
      try {
        py::object error_from_code =
            py::module_::import("cpp_quant_engine.exceptions").attr("error_from_code");
        exc = error_from_code(py::int_(e.code_value()), py::str(e.what()));
      } catch (...) {
        exc = py::module_::import("builtins").attr("RuntimeError")(py::str(e.what()));
      }
      PyErr_SetObject(reinterpret_cast<PyObject*>(Py_TYPE(exc.ptr())), exc.ptr());
    }
  });

  py::class_<Backend>(m, "Backend")
      .def(py::init([]() { return Backend(bridge::create_backend()); }))
      .def("meta", &Backend::meta)
      .def("version", &Backend::version)
      .def("market_data_load", &Backend::market_data_load, py::arg("request"))
      .def("statistics_compute", &Backend::statistics_compute, py::arg("request"))
      .def("risk_compute", &Backend::risk_compute, py::arg("request"))
      .def("simulation_run", &Backend::simulation_run, py::arg("request"))
      .def("backtest_run", &Backend::backtest_run, py::arg("request"),
           py::arg("signal") = py::none())
      .def("performance_analyze", &Backend::performance_analyze, py::arg("request"));

  py::class_<CppQuantBackend>(m, "CppQuantBackend")
      .def(py::init<>())
      .def("calculate_returns", &CppQuantBackend::calculate_returns,
           py::arg("prices"), py::arg("return_type") = "percentage")
.def("calculate_volatility", &CppQuantBackend::calculate_volatility,
           py::arg("returns"), py::arg("method") = "standard_deviation")
      .def("calculate_drawdown", &CppQuantBackend::calculate_drawdown,
           py::arg("equity_curve"))
      .def("calculate_statistics", &CppQuantBackend::calculate_statistics,
           py::arg("returns"))
      .def("calculate_metrics", &CppQuantBackend::calculate_metrics,
           py::arg("returns"), py::arg("equity_curve"),
           py::arg("risk_free_rate") = 0.0)
      .def("calculate_performance_analytics", &CppQuantBackend::calculate_performance_analytics,
           py::arg("returns"))
      .def("run_simulation", &CppQuantBackend::run_simulation,
           py::arg("request"), py::arg("prices"))
      .def("get_version", &CppQuantBackend::get_version)
      .def("mean", &CppQuantBackend::mean, py::arg("data"))
      .def("std_dev", &CppQuantBackend::std_dev, py::arg("data"))
      .def("variance", &CppQuantBackend::variance, py::arg("data"))
      .def("z_score", &CppQuantBackend::z_score,
           py::arg("value"), py::arg("mean"), py::arg("std"))
      .def("regression_slope", &CppQuantBackend::regression_slope, py::arg("y"))
      .def("regression_intercept", &CppQuantBackend::regression_intercept, py::arg("y"))
      .def("regression_correlation", &CppQuantBackend::regression_correlation,
           py::arg("x"), py::arg("y"))
      .def("regression_r_squared", &CppQuantBackend::regression_r_squared,
           py::arg("x"), py::arg("y"))
      .def("regression_standard_error", &CppQuantBackend::regression_standard_error,
           py::arg("x"), py::arg("y"))
      .def("rolling_mean", &CppQuantBackend::rolling_mean,
           py::arg("data"), py::arg("window"))
.def("rolling_volatility_series_ext", &CppQuantBackend::rolling_volatility_series_ext,
           py::arg("data"), py::arg("window"), py::arg("ddof") = 1)
      .def("rolling_variance_ext", &CppQuantBackend::rolling_variance_ext,
           py::arg("data"), py::arg("window"), py::arg("ddof") = 1);

  m.def("version", []() { return quant::Version::current().to_string(); },
        "Get the C++ Quant Engine version (major.minor.patch)");
  m.def("bridge_version", []() { return std::string(bridge::kBridgeVersion); },
        "Get the bridge contract version");
  m.def("protocol_version", []() { return bridge::kBridgeProtocolVersion; },
        "Get the bridge protocol version");
  m.def("supported_calculation_versions",
        []() { return bridge::supported_calculation_versions(); },
        "List of supported calculation version tokens");
  m.def("error_codes", []() {
    py::dict out;
    for (uint32_t v : {100u, 101u, 102u, 200u, 201u, 202u, 203u, 300u, 301u, 302u, 500u}) {
      auto code = static_cast<bridge::BridgeErrorCode>(v);
      out[bridge::bridge_error_name(code)] = v;
    }
    return out;
  }, "Stable bridge error codes (name -> numeric value)");
}
