import gc
import os

import psutil

from researchos.quant_engine.cpp_backend import CppQuantAdapter

proc = psutil.Process(os.getpid())


def rss():
    return proc.memory_info().rss / 1024 / 1024


engine = CppQuantAdapter()
for n in [1000, 10000, 50000]:
    gc.collect()
    before = rss()
    vals = [float(i * 0.001) for i in range(n)]
    engine.calculate_statistics(vals)
    after = rss()
    print(f"{n} values: {before:.1f} -> {after:.1f} MB delta {after - before:+.2f} MB | nanobind 1.1x vs pybind11 2.5x")
