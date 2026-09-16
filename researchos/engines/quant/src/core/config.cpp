#include <cmath>
#include "quant/core/config.h"
#include <format>
#include <optional>
#include <sstream>
#include <iomanip>
#include <stack>
#include <cctype>

namespace quant {

Config Config::object() { return Config(std::unordered_map<std::string, Config>{}); }
Config Config::array() { return Config(std::vector<Config>{}); }

bool Config::is_null() const { return std::holds_alternative<std::nullptr_t>(value_); }
bool Config::is_bool() const { return std::holds_alternative<bool>(value_); }
bool Config::is_int() const { return std::holds_alternative<int64_t>(value_); }
bool Config::is_double() const { return std::holds_alternative<double>(value_); }
bool Config::is_string() const { return std::holds_alternative<std::string>(value_); }
bool Config::is_array() const { return std::holds_alternative<std::vector<Config>>(value_); }
bool Config::is_object() const { return std::holds_alternative<std::unordered_map<std::string, Config>>(value_); }

Result<bool> Config::get_bool() const {
  if (!is_bool()) return Error(ErrorCode::ConfigTypeMismatch, "not a bool");
  return std::get<bool>(value_);
}

Result<int64_t> Config::get_int() const {
  if (!is_int()) return Error(ErrorCode::ConfigTypeMismatch, "not an int");
  return std::get<int64_t>(value_);
}

Result<double> Config::get_double() const {
  if (is_double()) return std::get<double>(value_);
  if (is_int()) return static_cast<double>(std::get<int64_t>(value_));
  return Error(ErrorCode::ConfigTypeMismatch, "not a number");
}

Result<std::string> Config::get_string() const {
  if (!is_string()) return Error(ErrorCode::ConfigTypeMismatch, "not a string");
  return std::get<std::string>(value_);
}

Result<std::vector<Config>> Config::get_array() const {
  if (!is_array()) return Error(ErrorCode::ConfigTypeMismatch, "not an array");
  return std::get<std::vector<Config>>(value_);
}

Config& Config::operator[](std::string_view key) {
  if (!is_object()) {
    value_ = std::unordered_map<std::string, Config>{};
  }
  auto& map = std::get<std::unordered_map<std::string, Config>>(value_);
  return map[std::string(key)];
}

const Config& Config::operator[](std::string_view key) const {
  static const Config null_config;
  if (!is_object()) return null_config;
  auto& map = std::get<std::unordered_map<std::string, Config>>(value_);
  auto it = map.find(std::string(key));
  return it != map.end() ? it->second : null_config;
}

void Config::set(std::string_view key, Config val) {
  (*this)[key] = std::move(val);
}

bool Config::has(std::string_view key) const {
  if (!is_object()) return false;
  auto& map = std::get<std::unordered_map<std::string, Config>>(value_);
  return map.find(std::string(key)) != map.end();
}

Result<Config> Config::get(std::string_view path) const {
  const Config* current = this;
  size_t start = 0;
  while (start < path.size()) {
    if (path[start] == '.') { ++start; continue; }
    size_t end = path.find('.', start);
    if (end == std::string_view::npos) end = path.size();
    auto key = path.substr(start, end - start);
    if (!current->is_object() || !current->has(key)) {
      return Error(ErrorCode::ConfigKeyNotFound, std::format("key '{}' not found in path '{}'", key, path));
    }
    current = &(*current)[key];
    start = end;
  }
  return *current;
}

void Config::push_back(Config val) {
  if (!is_array()) {
    value_ = std::vector<Config>{};
  }
  std::get<std::vector<Config>>(value_).push_back(std::move(val));
}

size_t Config::size() const {
  if (is_array()) return std::get<std::vector<Config>>(value_).size();
  if (is_object()) return std::get<std::unordered_map<std::string, Config>>(value_).size();
  return 0;
}

std::vector<std::string> Config::keys() const {
  if (!is_object()) return {};
  auto& map = std::get<std::unordered_map<std::string, Config>>(value_);
  std::vector<std::string> result;
  result.reserve(map.size());
  for (auto& [k, _] : map) result.push_back(k);
  return result;
}

void append_json(std::ostringstream& os, const Config& cfg, int indent = 0) {
  if (cfg.is_null()) { os << "null"; }
  else if (cfg.is_bool()) { os << (cfg.get_bool().value() ? "true" : "false"); }
  else if (cfg.is_int()) { os << cfg.get_int().value(); }
  else if (cfg.is_double()) {
    auto val = cfg.get_double().value();
    if (val == std::floor(val) && std::isfinite(val)) {
      os << std::fixed << std::setprecision(1) << val;
    } else {
      os << std::defaultfloat << std::setprecision(15) << val;
    }
  }
  else if (cfg.is_string()) {
    auto s = cfg.get_string().value();
    os << '"';
    for (char c : s) {
      if (c == '"') os << "\\\"";
      else if (c == '\\') os << "\\\\";
      else if (c == '\n') os << "\\n";
      else if (c == '\t') os << "\\t";
      else if (c == '\r') os << "\\r";
      else os << c;
    }
    os << '"';
  }
  else if (cfg.is_array()) {
    auto arr = cfg.get_array().value();
    os << '[';
    for (size_t i = 0; i < arr.size(); ++i) {
      if (i > 0) os << ",";
      append_json(os, arr[i], indent);
    }
    os << ']';
  }
  else if (cfg.is_object()) {
    os << '{';
    auto keys = cfg.keys();
    for (size_t i = 0; i < keys.size(); ++i) {
      if (i > 0) os << ",";
      os << '"' << keys[i] << "\":";
      append_json(os, cfg[keys[i]], indent);
    }
    os << '}';
  }
}

std::string Config::to_string() const {
  std::ostringstream os;
  append_json(os, *this);
  return os.str();
}

Config Config::parse_json(std::string_view json) {
  struct Parser {
    std::string_view s;
    size_t pos{0};

    void skip_ws() { while (pos < s.size() && std::isspace(s[pos])) ++pos; }

    std::optional<std::string> parse_string() {
      skip_ws();
      if (pos >= s.size() || s[pos] != '"') return std::nullopt;
      ++pos;
      std::string result;
      while (pos < s.size() && s[pos] != '"') {
        if (s[pos] == '\\' && pos + 1 < s.size()) {
          ++pos;
          switch (s[pos]) {
            case '"': result += '"'; break;
            case '\\': result += '\\'; break;
            case '/': result += '/'; break;
            case 'n': result += '\n'; break;
            case 't': result += '\t'; break;
            case 'r': result += '\r'; break;
            default: result += s[pos]; break;
          }
        } else {
          result += s[pos];
        }
        ++pos;
      }
      if (pos < s.size()) ++pos;
      return result;
    }

    Config parse_value() {
      skip_ws();
      if (pos >= s.size()) return Config();
      char c = s[pos];
      if (c == '"') {
        auto str = parse_string();
        return Config(str.value_or(""));
      }
      if (c == '{') return parse_object();
      if (c == '[') return parse_array();
      if (c == 't' && s.substr(pos, 4) == "true") { pos += 4; return Config(true); }
      if (c == 'f' && s.substr(pos, 5) == "false") { pos += 5; return Config(false); }
      if (c == 'n' && s.substr(pos, 4) == "null") { pos += 4; return Config(); }
      return parse_number();
    }

    Config parse_number() {
      skip_ws();
      size_t start = pos;
      if (pos < s.size() && (s[pos] == '-' || s[pos] == '+')) ++pos;
      while (pos < s.size() && std::isdigit(s[pos])) ++pos;
      bool is_float = false;
      if (pos < s.size() && s[pos] == '.') { is_float = true; ++pos; while (pos < s.size() && std::isdigit(s[pos])) ++pos; }
      if (pos < s.size() && (s[pos] == 'e' || s[pos] == 'E')) { is_float = true; ++pos; if (pos < s.size() && (s[pos] == '+' || s[pos] == '-')) ++pos; while (pos < s.size() && std::isdigit(s[pos])) ++pos; }
      std::string num_str(s.substr(start, pos - start));
      if (is_float) return Config(std::stod(num_str));
      return Config(static_cast<int64_t>(std::stoll(num_str)));
    }

    Config parse_object() {
      Config obj = Config::object();
      ++pos;
      skip_ws();
      if (pos < s.size() && s[pos] == '}') { ++pos; return obj; }
      while (pos < s.size()) {
        skip_ws();
        auto key = parse_string();
        if (!key) break;
        skip_ws();
        if (pos < s.size() && s[pos] == ':') ++pos;
        obj.set(*key, parse_value());
        skip_ws();
        if (pos < s.size() && s[pos] == ',') ++pos;
        else if (pos < s.size() && s[pos] == '}') { ++pos; break; }
        else break;
      }
      return obj;
    }

    Config parse_array() {
      Config arr = Config::array();
      ++pos;
      skip_ws();
      if (pos < s.size() && s[pos] == ']') { ++pos; return arr; }
      while (pos < s.size()) {
        arr.push_back(parse_value());
        skip_ws();
        if (pos < s.size() && s[pos] == ',') ++pos;
        else if (pos < s.size() && s[pos] == ']') { ++pos; break; }
        else break;
      }
      return arr;
    }
  };

  Parser parser{json, 0};
  return parser.parse_value();
}

} // namespace quant
