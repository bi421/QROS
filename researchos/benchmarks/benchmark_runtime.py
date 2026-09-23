import pathlib  # noqa: E402

# noqa: E402
import statistics  # noqa: E402

# noqa: E402
import sys  # noqa: E402

# noqa: E402
import timeit  # noqa: E402

# noqa: E402

sys.path.insert(0, "cpp_quant_engine/python")
from cpp_quant_engine.cpp_quant_backend import Backend  # noqa: E402

# noqa: E402


def make_candles(n=1000):
    return [{"timestamp": "2024-01-01T00:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0, "timeframe": "M1"} for _ in range(n)]


print("=== nanobind Benchmark ===")
b = Backend()
print(f"Backend meta: {b.meta()}")
p = pathlib.Path("cpp_quant_engine/python/cpp_quant_engine/cpp_quant_backend.cp314-win_amd64.pyd")
if p.exists():
    print(f"Binary: {p.stat().st_size / 1024:.0f}KB (pybind11 was 684KB+26MB PDB)")
inst = timeit.repeat("Backend()", setup="from cpp_quant_engine.cpp_quant_backend import Backend", number=1, repeat=500)
print(f"[Backend()] mean {statistics.mean(inst) * 1e6:.1f} us")
meta = timeit.repeat("b.meta()", globals={"b": b}, number=1, repeat=1000)
print(f"[b.meta()] mean {statistics.mean(meta) * 1e6:.1f} us")
import time as tm  # noqa: E402

# noqa: E402

data = make_candles(1000)
req = {"symbol": "EURUSD", "timeframe": "M1", "candles": data}
times = []
for _ in range(100):
    t0 = tm.perf_counter()
    b.market_data_load(req)
    times.append((tm.perf_counter() - t0) * 1000)
print(f"[market_data_load 1000] mean {statistics.mean(times):.2f} ms median {statistics.median(times):.2f} ms")
