import pybind11
from setuptools import Extension, setup

ext = Extension(
    "cpp_quant",
    sources=["python/bindings.cpp", "src/backtest.cpp"],
    include_dirs=[pybind11.get_include(), "include"],
    language="c++",
    extra_compile_args=["-std=c++17", "-O3", "/openmp"],
)

setup(name="cpp_quant", ext_modules=[ext])
