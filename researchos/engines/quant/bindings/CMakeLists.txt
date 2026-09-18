# Canonical Python binding for the QROS C++ Quant Engine.

if(NOT TARGET quant_engine)
    message(FATAL_ERROR "bindings/ must be configured from the root project")
endif()

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
        "nanobind CMake directory could not be discovered: ${NANOBIND_CMAKE_ERROR}"
    )
endif()

set(nanobind_ROOT "${NANOBIND_CMAKE_DIR}")

find_package(nanobind CONFIG REQUIRED)

nanobind_add_module(
    cpp_quant_backend
    python_bindings.cpp
)

target_link_libraries(
    cpp_quant_backend
    PRIVATE
        quant_engine
)

target_include_directories(
    cpp_quant_backend
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/../include
        ${CMAKE_CURRENT_SOURCE_DIR}/../python
)

target_compile_features(
    cpp_quant_backend
    PRIVATE
        cxx_std_20
)

set_target_properties(
    cpp_quant_backend
    PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
        RUNTIME_OUTPUT_DIRECTORY
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
)


# Install the nanobind extension into the importable top-level package.
# scikit-build-core installs CMake targets relative to the wheel's platlib root.
install(
    TARGETS cpp_quant_backend
    LIBRARY DESTINATION cpp_quant_engine
    RUNTIME DESTINATION cpp_quant_engine
)
