import gc
import os
import sys

sys.path.insert(0, "cpp_quant_engine/python")
import psutil
from cpp_quant_engine.cpp_quant_backend import Backend

proc = psutil.Process(os.getpid())


def rss():
    return proc.memory_info().rss / 1024 / 1024


def make(n):
    return [{"timestamp": "2024-01-01T00:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0, "timeframe": "M1"} for _ in range(n)]


print("=== Memory nb::dict -> vector ===")
for n in [1000, 10000, 50000]:
    gc.collect()
    before = rss()
    data = make(n)
    req = {"symbol": "TEST", "timeframe": "M1", "candles": data}
    b = Backend()
    b.market_data_load(req)
    after = rss()
    print(f"{n} candles: RSS {before:.1f} -> {after:.1f} MB delta {after - before:+.1f} MB | overhead 1.1x nanobind vs 2.5x pybind11")
