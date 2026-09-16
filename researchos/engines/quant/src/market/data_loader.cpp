#include "quant/market/data_loader.h"
#include "quant/core/logger.h"
#include <fstream>
#include <sstream>
#include <cstring>
#include <ctime>
#include <format>
#include <iomanip>
#include <algorithm>

namespace quant {

DataLoader::DataLoader(std::string symbol) : symbol_(std::move(symbol)) {}

TimePoint DataLoader::parse_datetime(const std::string& str, const std::string& fmt) {
  std::tm tm = {};
  std::istringstream ss(str);
  ss >> std::get_time(&tm, fmt.c_str());
  if (ss.fail()) {
    // Try ISO 8601 fallback
    std::istringstream ss2(str);
    ss2 >> std::get_time(&tm, "%Y-%m-%dT%H:%M:%S");
    if (ss2.fail()) {
      ss2.clear();
      ss2.str(str);
      ss2 >> std::get_time(&tm, "%Y.%m.%d %H:%M:%S");
    }
  }
  auto time = std::mktime(&tm);
  return std::chrono::system_clock::from_time_t(time);
}

std::string DataLoader::format_datetime(TimePoint tp, const std::string& fmt) {
  auto time_t = std::chrono::system_clock::to_time_t(tp);
  std::tm tm{};
#ifdef _WIN32
  gmtime_s(&tm, &time_t);
#else
  gmtime_r(&time_t, &tm);
#endif
  std::ostringstream ss;
  ss << std::put_time(&tm, fmt.c_str());
  return ss.str();
}

Result<OHLCVContainer> DataLoader::load_file(const std::filesystem::path& path,
                                              const LoadConfig& cfg) {
  if (!std::filesystem::exists(path)) {
    return Error(ErrorCode::FileNotFound,
                 std::format("file not found: {}", path.string()));
  }

  auto ext = path.extension().string();
  std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);

  LoadConfig config = cfg;
  if (config.format == FileFormat::CSV || ext == ".csv") {
    return load_csv(path, config);
  }

  return Error(ErrorCode::InvalidArgument,
               std::format("unsupported file format: {}", ext));
}

Result<OHLCVContainer> DataLoader::load_csv(const std::filesystem::path& path,
                                             const LoadConfig& cfg) {
  std::ifstream file(path);
  if (!file.is_open()) {
    return Error(ErrorCode::FileNotFound,
                 std::format("cannot open file: {}", path.string()));
  }

  std::stringstream buffer;
  buffer << file.rdbuf();
  auto data_str = buffer.str();
  auto candles = parse_csv_string(data_str, cfg);
  if (candles.is_err()) return candles.error();

  std::string sym = symbol_.empty() ? path.stem().string() : symbol_;
  OHLCVContainer container(sym, cfg.target_timeframe);
  auto r = container.append_batch(candles.value());
  if (r.is_err()) return r.error();

  auto log_msg = std::format("Loaded {} candles from {} ({} -> {})",
                              container.size(), path.string(),
                              DataLoader::format_datetime(container.first_time()),
                              DataLoader::format_datetime(container.last_time()));
  Logger::instance().info(log_msg);
  return container;
}

Result<std::vector<Candle>> DataLoader::parse_csv_string(std::string_view data,
                                                          const LoadConfig& cfg) {
  std::vector<Candle> candles;
  candles.reserve(100000);

  auto data_copy = std::string(data);
  std::istringstream stream(data_copy);
  std::string line;
  size_t line_num = 0;

  while (std::getline(stream, line)) {
    ++line_num;
    if (line.empty()) continue;
    if (cfg.has_header && line_num == 1) continue;

    std::vector<std::string> cols;
    std::istringstream line_stream(line);
    std::string col;
    while (std::getline(line_stream, col, cfg.delimiter)) {
      cols.push_back(col);
    }

    size_t needed = std::max({cfg.col_timestamp, cfg.col_open, cfg.col_high,
                               cfg.col_low, cfg.col_close, cfg.col_volume}) + 1;
    if (cols.size() < needed) continue;

    auto trim = [](std::string& s) {
      s.erase(0, s.find_first_not_of(" \t\r\n"));
      s.erase(s.find_last_not_of(" \t\r\n") + 1);
    };

    for (auto& c : cols) trim(c);

    Candle candle;
    candle.timestamp = parse_datetime(cols[cfg.col_timestamp], cfg.datetime_format);
    candle.open = std::stod(cols[cfg.col_open]);
    candle.high = std::stod(cols[cfg.col_high]);
    candle.low = std::stod(cols[cfg.col_low]);
    candle.close = std::stod(cols[cfg.col_close]);
    candle.volume = std::stod(cols[cfg.col_volume]);
    candle.timeframe = cfg.target_timeframe;

    if (!candle.is_valid()) {
      return Error(ErrorCode::InvalidArgument,
                   std::format("invalid candle at line {}", line_num));
    }

    candles.push_back(candle);
  }

  return candles;
}

Result<std::vector<OHLCVContainer>> DataLoader::load_directory(
    const std::filesystem::path& dir, const LoadConfig& cfg) {
  if (!std::filesystem::exists(dir) || !std::filesystem::is_directory(dir)) {
    return Error(ErrorCode::FileNotFound,
                 std::format("directory not found: {}", dir.string()));
  }

  std::vector<OHLCVContainer> containers;
  for (const auto& entry : std::filesystem::directory_iterator(dir)) {
    if (entry.is_regular_file()) {
      auto ext = entry.path().extension().string();
      std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);
      if (ext == ".csv" || ext == ".txt" || ext == ".data") {
        auto result = load_csv(entry.path(), cfg);
        if (result.is_ok()) {
          containers.push_back(std::move(result.value()));
        }
      }
    }
  }

  return containers;
}

} // namespace quant
