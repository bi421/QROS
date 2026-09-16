cmake_minimum_required(VERSION 3.20)
project(cpp_quant_engine VERSION 1.1.0 LANGUAGES CXX)

# ── C++20 Standard ──────────────────────────────────────────────────────────
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# ── Build Options ────────────────────────────────────────────────────────────
option(BUILD_SHARED_LIBS "Build shared library" OFF)
option(BUILD_TESTS "Build C++ unit tests" ON)
option(BUILD_BENCHMARKS "Build benchmarks" ON)
option(BUILD_PYTHON_BINDINGS "Build pybind11 Python bindings" OFF)

# ── Include Directories ──────────────────────────────────────────────────────
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/include)

# ── Sources ──────────────────────────────────────────────────────────────────
file(GLOB_RECURSE QUANT_SOURCES CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp")

# ── Core Library ─────────────────────────────────────────────────────────────
add_library(quant_engine STATIC ${QUANT_SOURCES})

target_include_directories(quant_engine PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}/python
)
target_compile_features(quant_engine PUBLIC cxx_std_20)

# MSVC: structured exceptions + UTF-8 source. Others: disable exceptions/RTTI.
target_compile_options(quant_engine PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:/EHsc /utf-8>
    $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-fexceptions -frtti>
)

# ── Python Bindings (optional) ───────────────────────────────────────────────
if(BUILD_PYTHON_BINDINGS)
    # The bridge uses exceptions (BridgeError), so ensure they are enabled.
    if(NOT MSVC)
        target_compile_options(quant_engine PRIVATE -fexceptions -frtti)
    endif()

    find_package(pybind11 CONFIG QUIET)
    if(NOT pybind11_FOUND)
        # Discover the pybind11 CMake config installed with the active Python.
        find_package(Python3 COMPONENTS Interpreter QUIET)
        if(Python3_FOUND)
            execute_process(
                COMMAND "${Python3_EXECUTABLE}" -m pybind11 --cmakedir
                OUTPUT_VARIABLE PYBIND11_CMAKE_DIR
                OUTPUT_STRIP_TRAILING_WHITESPACE
                RESULT_VARIABLE PYBIND11_CMAKE_RC
                ERROR_QUIET)
            if(PYBIND11_CMAKE_RC EQUAL 0 AND PYBIND11_CMAKE_DIR)
                set(pybind11_DIR "${PYBIND11_CMAKE_DIR}" CACHE PATH
                    "pybind11 CMake config directory" FORCE)
            endif()
        endif()
        unset(pybind11_FOUND CACHE)
        find_package(pybind11 CONFIG QUIET)
    endif()

    if(pybind11_FOUND)
        message(STATUS "pybind11 found: ${pybind11_INCLUDE_DIRS}")
        # python3_add_library (used internally by pybind11_add_module) requires
        # the Python Development module to be loaded.
        find_package(Python3 COMPONENTS Development QUIET)
        pybind11_add_module(cpp_quant_backend
            bindings/python_bindings.cpp
        )
        target_link_libraries(cpp_quant_backend PRIVATE quant_engine)
        target_include_directories(cpp_quant_backend
            PRIVATE
                ${CMAKE_CURRENT_SOURCE_DIR}/include
                ${CMAKE_CURRENT_SOURCE_DIR}/python
        )
        target_compile_features(cpp_quant_backend PRIVATE cxx_std_20)
        set_target_properties(cpp_quant_backend PROPERTIES
            LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/python/cpp_quant_engine"
            LIBRARY_OUTPUT_DIRECTORY_DEBUG "${CMAKE_CURRENT_SOURCE_DIR}/python/cpp_quant_engine"
            LIBRARY_OUTPUT_DIRECTORY_RELEASE "${CMAKE_CURRENT_SOURCE_DIR}/python/cpp_quant_engine"
        )
    else()
        message(WARNING "pybind11 not found — Python bindings will NOT be built")
    endif()
endif()

# ── C++ Unit Tests ───────────────────────────────────────────────────────────
if(BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()

# ── Benchmarks ───────────────────────────────────────────────────────────────
if(BUILD_BENCHMARKS)
    add_subdirectory(benchmarks)
endif()

# ── Install ──────────────────────────────────────────────────────────────────
install(TARGETS quant_engine
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    INCLUDES DESTINATION include
)

install(DIRECTORY include/ DESTINATION include)
