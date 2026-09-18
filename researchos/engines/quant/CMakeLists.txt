cmake_minimum_required(VERSION 3.20)
project(cpp_quant_engine VERSION 1.1.0 LANGUAGES CXX)

# C++20 Standard
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Build Options
option(BUILD_SHARED_LIBS "Build shared library" OFF)
option(BUILD_TESTS "Build C++ unit tests" ON)
option(BUILD_BENCHMARKS "Build benchmarks" ON)
option(BUILD_PYTHON_BINDINGS "Build nanobind Python bindings" ON)

# Include Directories
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/include)

# Sources
file(GLOB_RECURSE QUANT_SOURCES CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp")

# Core Library
add_library(quant_engine STATIC ${QUANT_SOURCES})

target_include_directories(quant_engine PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}/python
)
target_compile_features(quant_engine PUBLIC cxx_std_20)

# MSVC: structured exceptions + UTF-8 source
target_compile_options(quant_engine PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:/EHsc /utf-8>
    $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-fexceptions -frtti>
)

# Python Bindings (optional)
if(BUILD_PYTHON_BINDINGS)
    find_package(Python COMPONENTS Interpreter Development REQUIRED)
    find_package(Python3 COMPONENTS Interpreter Development REQUIRED)

    execute_process(
        COMMAND "${Python3_EXECUTABLE}" -m nanobind --cmake_dir
        OUTPUT_VARIABLE NANOBIND_CMAKE_DIR
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE NANOBIND_CMAKE_RC
        ERROR_VARIABLE NANOBIND_CMAKE_ERROR
    )

    if(NOT NANOBIND_CMAKE_RC EQUAL 0 OR NOT NANOBIND_CMAKE_DIR)
        message(FATAL_ERROR
            "nanobind CMake directory could not be discovered from active Python: ${NANOBIND_CMAKE_ERROR}"
        )
    endif()

    set(nanobind_ROOT "${NANOBIND_CMAKE_DIR}")
    find_package(nanobind CONFIG REQUIRED)
    add_subdirectory(bindings)
endif()

# C++ Unit Tests
if(BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()

# Benchmarks
if(BUILD_BENCHMARKS)
    add_subdirectory(benchmarks)
endif()

# Install
install(TARGETS quant_engine
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    INCLUDES DESTINATION include
)

install(DIRECTORY include/ DESTINATION include)