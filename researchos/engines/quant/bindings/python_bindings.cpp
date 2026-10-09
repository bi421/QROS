#include <cmath>
// nanobind bindings exposing the C++ Quant Engine to Python.
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

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/map.h>
#include <nanobind/stl/unordered_map.h>
#include <nanobind/stl/function.h>




#include "bridge_interface.h"
#include "bridge_models.h"
#include "bridge_validation.h"
#include "quant/backtest/serialization.h"
#include "quant/core/engine.h"
#include "quant/statistics/regression.h"
#include "quant/statistics/rolling.h"
#include "quant/low_latency/turing_filter.h"
#include "quant/parallel/research_wave.h"

#include "quant_engine.hpp"

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace nb = nanobind;
using namespace nanobind::literals;
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

std::string get_str(const nb::dict& d, const char* key, const char* def = "") {
  if (d.contains(key) && !d[key].is_none()) return nb::cast<std::string>(d[key]);
  return def;
}

double get_double(const nb::dict& d, const char* key, double def = 0.0) {
  if (d.contains(key) && !d[key].is_none()) return nb::cast<double>(d[key]);
  return def;
}

int get_int(const nb::dict& d, const char* key, int def = 0) {
  if (d.contains(key) && !d[key].is_none()) return nb::cast<int>(d[key]);
  return def;
}

bool get_bool(const nb::dict& d, const char* key, bool def = false) {
  if (d.contains(key) && !d[key].is_none()) return nb::cast<bool>(d[key]);
  return def;
}

std::vector<double> get_double_list(const nb::dict& d, const char* key) {
  if (d.contains(key)) {
    if (d[key].is_none())
      throw bridge::BridgeError(bridge::BridgeErrorCode::InvalidType,
                                "expected a list for '" + std::string(key) + "', got None");
    return nb::cast<std::vector<double>>(d[key]);
  }
  return {};
}

CandleModel candle_from_dict(const nb::dict& c) {
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

std::vector<CandleModel> get_candle_list(const nb::dict& d, const char* key) {
  std::vector<CandleModel> out;
  if (!d.contains(key)) return out;
  if (d[key].is_none())
    throw bridge::BridgeError(bridge::BridgeErrorCode::InvalidType,
                              "expected a list for '" + std::string(key) + "', got None");
  const auto list = nb::cast<nb::list>(d[key]);
  out.reserve(list.size());
  for (const auto& item : list) out.push_back(candle_from_dict(nb::cast<nb::dict>(item)));
  return out;
}

nb::dict candle_to_dict(const CandleModel& c) {
  nb::dict out;
  out["timestamp"] = c.timestamp;
  out["open"] = c.open;
  out["high"] = c.high;
  out["low"] = c.low;
  out["close"] = c.close;
  out["volume"] = c.volume;
  out["timeframe"] = c.timeframe;
  return out;
}

nb::dict meta_to_dict(const bridge::BridgeMeta& m) {
  nb::dict out;
  out["engine_name"] = m.engine_name;
  out["engine_version"] = m.engine_version;
  out["bridge_version"] = m.bridge_version;
  out["protocol_version"] = m.protocol_version;
  out["calculation_version"] = m.calculation_version;
  return out;
}

nb::dict market_data_result_to_dict(const bridge::MarketDataResult& r) {
  nb::dict out;
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

nb::dict statistics_result_to_dict(const bridge::StatisticsResult& r) {
  nb::dict out;
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

nb::dict risk_result_to_dict(const bridge::RiskResult& r) {
  nb::dict out;
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

nb::dict simulation_result_to_dict(const bridge::SimulationResult& r) {
  nb::dict out;
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

nb::dict backtest_result_to_dict(const bridge::BacktestResult& r) {
  nb::dict out;
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

nb::dict performance_result_to_dict(const bridge::PerformanceResult& r) {
  nb::dict out;
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
std::optional<quant::SignalFn> make_signal_fn(const nb::object& signal) {
  if (signal.is_none()) return std::nullopt;
  nb::object fn = signal;
  return [fn](size_t bar_index, const std::vector<quant::OHLCV>& history)
             -> quant::SignalResult {
    nb::gil_scoped_acquire gil;
    nb::list hist;
    for (const auto& b : history) {
      nb::dict d;
      d["timestamp"] = quant::serialization::to_iso8601(b.timestamp);
      d["open"] = b.open;
      d["high"] = b.high;
      d["low"] = b.low;
      d["close"] = b.close;
      d["volume"] = b.volume;
      hist.append(d);
    }
    nb::object res = fn(nb::int_(bar_index), hist);
    nb::dict rd = nb::cast<nb::dict>(res);
    quant::SignalResult sr;
    sr.direction = (nb::cast<int>(rd["direction"]) == 0)
                       ? quant::TradeDirection::Buy
                       : quant::TradeDirection::Sell;
    sr.quantity = nb::cast<double>(rd["quantity"]);
    if (rd.contains("stop_loss")) sr.stop_loss = nb::cast<double>(rd["stop_loss"]);
    if (rd.contains("take_profit")) sr.take_profit = nb::cast<double>(rd["take_profit"]);
    return sr;
  };
}

} // namespace

// ── Stable Backend (Python/C++ integration contract) ────────────────────────

class Backend {
public:
  explicit Backend(std::shared_ptr<bridge::IBridgeBackend> impl)
      : impl_(std::move(impl)) {}

  nb::dict meta() const { return meta_to_dict(impl_->meta()); }

  nb::str version() const { return nb::str(impl_->version().c_str()); }

  nb::dict market_data_load(const nb::dict& request) const {
    MarketDataRequest req;
    req.symbol = get_str(request, "symbol");
    req.timeframe = get_str(request, "timeframe", "M1");
    req.candles = get_candle_list(request, "candles");
    req.calculation_version =
        get_str(request, "calculation_version", bridge::kDefaultCalculationVersion);
    return market_data_result_to_dict(impl_->market_data_load(req));
  }

  nb::dict statistics_compute(const nb::dict& request) const {
    StatisticsRequest req;
    req.data = get_double_list(request, "data");
    req.calculation_version =
        get_str(request, "calculation_version", bridge::kDefaultCalculationVersion);
    return statistics_result_to_dict(impl_->statistics_compute(req));
  }

  nb::dict risk_compute(const nb::dict& request) const {
    RiskRequest req;
    req.returns = get_double_list(request, "returns");
    req.equity_curve = get_double_list(request, "equity_curve");
    req.risk_free_rate = get_double(request, "risk_free_rate");
    req.calculation_version =
        get_str(request, "calculation_version", bridge::kDefaultCalculationVersion);
    return risk_result_to_dict(impl_->risk_compute(req));
  }

  nb::dict simulation_run(const nb::dict& request) const {
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

  nb::dict backtest_run(const nb::dict& request,
                        const nb::object& signal = nb::none()) const {
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

  nb::dict performance_analyze(const nb::dict& request) const {
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

  std::unordered_map<std::string, nb::object> run_simulation(
      const std::unordered_map<std::string, nb::object>& request_dict,
      const std::vector<double>& prices) {
    qe::simulation::SimulationInput input;
    auto get_str = [&](const std::string& key, const std::string& default_val) {
      auto it = request_dict.find(key);
      if (it != request_dict.end()) return nb::cast<std::string>(it->second);
      return default_val;
    };
    auto get_double = [&](const std::string& key, double default_val) {
      auto it = request_dict.find(key);
      if (it != request_dict.end()) return nb::cast<double>(it->second);
      return default_val;
    };
    auto get_int = [&](const std::string& key, int default_val) {
      auto it = request_dict.find(key);
      if (it != request_dict.end()) return nb::cast<int>(it->second);
      return default_val;
    };

    input.dataset_reference = get_str("dataset_reference", "");
    input.dataset_version = get_str("dataset_version", "1.0.0");
    input.calculation_version = get_str("calculation_version", "CALCULATION_V1");
    input.initial_capital = get_double("initial_capital", 100000.0);
    input.risk_free_rate = get_double("risk_free_rate", 0.0);
    input.seed = get_int("seed", 42);

    auto output = qe::simulation::run_simulation(input, prices);

    std::unordered_map<std::string, nb::object> result;
    result["returns"] = nb::cast(output.returns);
    result["equity_curve"] = nb::cast(output.equity_curve);
    result["metrics"] = nb::cast(output.metrics);
    result["statistics"] = nb::cast(output.statistics);
    result["performance"] = nb::cast(output.performance);
    result["input_hash"] = nb::cast(output.input_hash);
    result["result_hash"] = nb::cast(output.result_hash);
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

// Static exception translator to avoid MSVC lambda conversion issues
static void bridge_exception_translator(std::exception_ptr p, void*) {
  try {
    if (p) std::rethrow_exception(p);
  } catch (const bridge::BridgeError& e) {
    nb::object exc;
    try {
      nb::object error_from_code =
          nb::module_::import_("cpp_quant_engine.exceptions").attr("error_from_code");
      exc = error_from_code(nb::int_(e.code_value()), nb::str(e.what()));
    } catch (...) {
      exc = nb::module_::import_("builtins").attr("RuntimeError")(nb::str(e.what()));
    }
    PyErr_SetObject(reinterpret_cast<PyObject*>(Py_TYPE(exc.ptr())), exc.ptr());
  }
}

NB_MODULE(cpp_quant_backend, m) {
  m.doc() = "C++20 Quant Computation Engine for ResearchOS — stable Python/C++ integration bridge";

  // Bridge errors are raised as the typed Python exceptions defined in
  // cpp_quant_engine/exceptions.py (selected by the stable numeric code).
  nb::register_exception_translator(reinterpret_cast<nanobind::detail::exception_translator>(&bridge_exception_translator));

  nb::class_<Backend>(m, "Backend")
      .def("__init__", [](Backend &self) { new (&self) Backend(bridge::create_backend()); })
      .def("meta", &Backend::meta)
      .def("version", &Backend::version)
      .def("market_data_load", &Backend::market_data_load, nb::arg("request"))
      .def("statistics_compute", &Backend::statistics_compute, nb::arg("request"))
      .def("risk_compute", &Backend::risk_compute, nb::arg("request"))
      .def("simulation_run", &Backend::simulation_run, nb::arg("request"))
      .def("backtest_run", &Backend::backtest_run, nb::arg("request"),
           nb::arg("signal") = nb::none())
      .def("performance_analyze", &Backend::performance_analyze, nb::arg("request"));

  nb::class_<CppQuantBackend>(m, "CppQuantBackend")
      .def(nb::init<>())
      .def("calculate_returns", &CppQuantBackend::calculate_returns,
           nb::arg("prices"), nb::arg("return_type") = "percentage")
.def("calculate_volatility", &CppQuantBackend::calculate_volatility,
           nb::arg("returns"), nb::arg("method") = "standard_deviation")
      .def("calculate_drawdown", &CppQuantBackend::calculate_drawdown,
           nb::arg("equity_curve"))
      .def("calculate_statistics", &CppQuantBackend::calculate_statistics,
           nb::arg("returns"))
      .def("calculate_metrics", &CppQuantBackend::calculate_metrics,
           nb::arg("returns"), nb::arg("equity_curve"),
           nb::arg("risk_free_rate") = 0.0)
      .def("calculate_performance_analytics", &CppQuantBackend::calculate_performance_analytics,
           nb::arg("returns"))
      .def("run_simulation", &CppQuantBackend::run_simulation,
           nb::arg("request"), nb::arg("prices"))
      .def("get_version", &CppQuantBackend::get_version)
      .def("mean", &CppQuantBackend::mean, nb::arg("data"))
      .def("std_dev", &CppQuantBackend::std_dev, nb::arg("data"))
      .def("variance", &CppQuantBackend::variance, nb::arg("data"))
      .def("z_score", &CppQuantBackend::z_score,
           nb::arg("value"), nb::arg("mean"), nb::arg("std"))
      .def("regression_slope", &CppQuantBackend::regression_slope, nb::arg("y"))
      .def("regression_intercept", &CppQuantBackend::regression_intercept, nb::arg("y"))
      .def("regression_correlation", &CppQuantBackend::regression_correlation,
           nb::arg("x"), nb::arg("y"))
      .def("regression_r_squared", &CppQuantBackend::regression_r_squared,
           nb::arg("x"), nb::arg("y"))
      .def("regression_standard_error", &CppQuantBackend::regression_standard_error,
           nb::arg("x"), nb::arg("y"))
      .def("rolling_mean", &CppQuantBackend::rolling_mean,
           nb::arg("data"), nb::arg("window"))
.def("rolling_volatility_series_ext", &CppQuantBackend::rolling_volatility_series_ext,
           nb::arg("data"), nb::arg("window"), nb::arg("ddof") = 1)
      .def("rolling_variance_ext", &CppQuantBackend::rolling_variance_ext,
           nb::arg("data"), nb::arg("window"), nb::arg("ddof") = 1);

  using TuringReadOnly1D =
      nb::ndarray<const double, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
  using TuringReadOnlyI64 =
      nb::ndarray<const std::int64_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
  using TuringWritableU8 =
      nb::ndarray<std::uint8_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;

  nb::enum_<quant::low_latency::TuringFilterDecision>(m, "TuringFilterDecision")
      .value("Drop", quant::low_latency::TuringFilterDecision::Drop)
      .value("Continue", quant::low_latency::TuringFilterDecision::Continue)
      .value("Accept", quant::low_latency::TuringFilterDecision::Accept)
      .value("Reject", quant::low_latency::TuringFilterDecision::Reject);

  nb::class_<quant::low_latency::TuringFilterTick>(m, "TuringFilterTick")
      .def(nb::init<>())
      .def_rw("timestamp_ns", &quant::low_latency::TuringFilterTick::timestamp_ns)
      .def_rw("bid", &quant::low_latency::TuringFilterTick::bid)
      .def_rw("ask", &quant::low_latency::TuringFilterTick::ask)
      .def_rw("bid_volume", &quant::low_latency::TuringFilterTick::bid_volume)
      .def_rw("ask_volume", &quant::low_latency::TuringFilterTick::ask_volume)
      .def_rw("trade_volume", &quant::low_latency::TuringFilterTick::trade_volume);

  nb::class_<quant::low_latency::TuringFilterConfig>(m, "TuringFilterConfig")
      .def(nb::init<>())
      .def_rw("max_spread", &quant::low_latency::TuringFilterConfig::max_spread)
      .def_rw("min_total_depth", &quant::low_latency::TuringFilterConfig::min_total_depth)
      .def_rw("min_trade_volume", &quant::low_latency::TuringFilterConfig::min_trade_volume)
      .def_rw("min_abs_imbalance", &quant::low_latency::TuringFilterConfig::min_abs_imbalance)
      .def_rw("min_persistence", &quant::low_latency::TuringFilterConfig::min_persistence)
      .def_rw("max_samples", &quant::low_latency::TuringFilterConfig::max_samples)
      .def_rw("event_probability_h", &quant::low_latency::TuringFilterConfig::event_probability_h)
      .def_rw("event_probability_not_h", &quant::low_latency::TuringFilterConfig::event_probability_not_h)
      .def_rw("contradiction_probability_h",
              &quant::low_latency::TuringFilterConfig::contradiction_probability_h)
      .def_rw("contradiction_probability_not_h",
              &quant::low_latency::TuringFilterConfig::contradiction_probability_not_h)
      .def_rw("lower_deciban", &quant::low_latency::TuringFilterConfig::lower_deciban)
      .def_rw("upper_deciban", &quant::low_latency::TuringFilterConfig::upper_deciban);

  nb::class_<quant::low_latency::TuringFilterState>(m, "TuringFilterState")
      .def_ro("log_odds_deciban", &quant::low_latency::TuringFilterState::log_odds_deciban)
      .def_ro("samples", &quant::low_latency::TuringFilterState::samples)
      .def_ro("persistence", &quant::low_latency::TuringFilterState::persistence)
      .def_ro("constraint_mask", &quant::low_latency::TuringFilterState::constraint_mask)
      .def_ro("last_decision", &quant::low_latency::TuringFilterState::last_decision)
      .def_ro("has_previous", &quant::low_latency::TuringFilterState::has_previous)
      .def_ro("last_timestamp_ns", &quant::low_latency::TuringFilterState::last_timestamp_ns)
      .def_ro("last_mid", &quant::low_latency::TuringFilterState::last_mid)
      .def_ro("last_directional_imbalance",
              &quant::low_latency::TuringFilterState::last_directional_imbalance);

  nb::class_<quant::low_latency::TuringSprtThresholds>(m, "TuringSprtThresholds")
      .def_ro("lower_deciban", &quant::low_latency::TuringSprtThresholds::lower_deciban)
      .def_ro("upper_deciban", &quant::low_latency::TuringSprtThresholds::upper_deciban);

  nb::class_<quant::low_latency::TuringFilterEngine>(m, "TuringFilterEngine")
      .def(nb::init<const quant::low_latency::TuringFilterConfig&, bool>(),
           nb::arg("config"), nb::arg("bullish_hypothesis") = true)
      .def("process", &quant::low_latency::TuringFilterEngine::process,
           nb::arg("tick"))
      .def("reset", &quant::low_latency::TuringFilterEngine::reset)
      .def("state", &quant::low_latency::TuringFilterEngine::state,
           nb::rv_policy::reference_internal)
      .def("bullish_hypothesis",
           &quant::low_latency::TuringFilterEngine::bullish_hypothesis)
      .def_static("thresholds_from_error_rates",
                  &quant::low_latency::TuringFilterEngine::thresholds_from_error_rates,
                  nb::arg("alpha"), nb::arg("beta"))
      .def_static("evidence_deciban",
                  &quant::low_latency::TuringFilterEngine::evidence_deciban,
                  nb::arg("p_event_h"), nb::arg("p_event_not_h"));

  m.def("turing_filter_batch",
        [](TuringReadOnlyI64 timestamp_ns, TuringReadOnly1D bid, TuringReadOnly1D ask,
           TuringReadOnly1D bid_volume, TuringReadOnly1D ask_volume,
           TuringReadOnly1D trade_volume,
           const quant::low_latency::TuringFilterConfig& config,
           bool bullish_hypothesis, TuringWritableU8 decisions) {
          const std::size_t n = timestamp_ns.shape(0);
          if (bid.shape(0) != n || ask.shape(0) != n ||
              bid_volume.shape(0) != n || ask_volume.shape(0) != n ||
              trade_volume.shape(0) != n || decisions.shape(0) != n) {
            throw std::invalid_argument(
                "all Turing filter buffers must have equal length");
          }
          quant::low_latency::TuringFilterEngine engine(config, bullish_hypothesis);
          nb::gil_scoped_release release;
          for (std::size_t i = 0; i < n; ++i) {
            quant::low_latency::TuringFilterTick tick;
            tick.timestamp_ns = timestamp_ns.data()[i];
            tick.bid = bid.data()[i];
            tick.ask = ask.data()[i];
            tick.bid_volume = bid_volume.data()[i];
            tick.ask_volume = ask_volume.data()[i];
            tick.trade_volume = trade_volume.data()[i];
            decisions.data()[i] =
                static_cast<std::uint8_t>(engine.process(tick));
          }
        },
        nb::arg("timestamp_ns").noconvert(),
        nb::arg("bid").noconvert(),
        nb::arg("ask").noconvert(),
        nb::arg("bid_volume").noconvert(),
        nb::arg("ask_volume").noconvert(),
        nb::arg("trade_volume").noconvert(),
        nb::arg("config"),
        nb::arg("bullish_hypothesis") = true,
        nb::arg("decisions").noconvert(),
        "Zero-copy Turing-inspired structural/anchor/SPRT filter.");

  m.def("parallel_research_wave",
        [](const std::vector<double>& values) {
          for (double value : values) {
            if (!std::isfinite(value)) {
              throw nb::value_error("research wave input contains non-finite value");
            }
          }
          quant::parallel::ResearchWaveResult result;
          {
            nb::gil_scoped_release release;
            result = quant::parallel::run_research_wave(values);
          }
          nb::dict out;
          out["mean"] = result.mean;
          out["variance"] = result.variance;
          out["standard_deviation"] = result.standard_deviation;
          out["linear_slope"] = result.linear_slope;
          out["positive_rate"] = result.positive_rate;
          out["sample_size"] = result.sample_size;
          return out;
        },
        nb::arg("values"),
        "Run independent deterministic research measurements in parallel over one immutable snapshot.");

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
    nb::dict out;
    for (uint32_t v : {100u, 101u, 102u, 200u, 201u, 202u, 203u, 300u, 301u, 302u, 500u}) {
      auto code = static_cast<bridge::BridgeErrorCode>(v);
      out[bridge::bridge_error_name(code)] = v;
    }
    return out;
  }, "Stable bridge error codes (name -> numeric value)");
}
