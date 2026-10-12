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
        LIBRARY_OUTPUT_DIRECTORY_RELEASE
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
        RUNTIME_OUTPUT_DIRECTORY_RELEASE
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
)


# Install the nanobind extension into the importable top-level package.
# scikit-build-core installs CMake targets relative to the wheel's platlib root.
install(
    TARGETS cpp_quant_backend
    LIBRARY DESTINATION cpp_quant_engine
    RUNTIME DESTINATION cpp_quant_engine
)


# Separate bounded candidate-probability kernel. Kept isolated from the legacy
# bridge so its zero-copy array contract and performance can be tested directly.
nanobind_add_module(
    qros_constraint_engine
    constraint_first.cpp
)

target_link_libraries(
    qros_constraint_engine
    PRIVATE
        quant_engine
)

target_compile_features(
    qros_constraint_engine
    PRIVATE
        cxx_std_20
)

set_target_properties(
    qros_constraint_engine
    PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
        RUNTIME_OUTPUT_DIRECTORY
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
        LIBRARY_OUTPUT_DIRECTORY_RELEASE
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
        RUNTIME_OUTPUT_DIRECTORY_RELEASE
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
)

install(
    TARGETS qros_constraint_engine
    LIBRARY DESTINATION cpp_quant_engine
    RUNTIME DESTINATION cpp_quant_engine
)


# Deterministic microstructure kernels. Inputs are borrowed contiguous NumPy
# buffers (no input copy); returned arrays own their result storage.
nanobind_add_module(
    qros_microstructure
    microstructure.cpp
)

target_link_libraries(
    qros_microstructure
    PRIVATE
        quant_engine
)

target_compile_features(
    qros_microstructure
    PRIVATE
        cxx_std_20
)

target_include_directories(
    qros_microstructure
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/../include
)

set_target_properties(
    qros_microstructure
    PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
        RUNTIME_OUTPUT_DIRECTORY
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
        LIBRARY_OUTPUT_DIRECTORY_RELEASE
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
        RUNTIME_OUTPUT_DIRECTORY_RELEASE
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
)

install(
    TARGETS qros_microstructure
    LIBRARY DESTINATION cpp_quant_engine
    RUNTIME DESTINATION cpp_quant_engine
)


# Isolated deterministic latency/slippage model. This is research math only;
# it does not place orders or claim a guaranteed execution price.
nanobind_add_module(
    qros_latency
    latency.cpp
)

target_link_libraries(
    qros_latency
    PRIVATE
        quant_engine
)

target_include_directories(
    qros_latency
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/../include
)

target_compile_features(
    qros_latency
    PRIVATE
        cxx_std_20
)

set_target_properties(
    qros_latency
    PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
        RUNTIME_OUTPUT_DIRECTORY
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
        LIBRARY_OUTPUT_DIRECTORY_RELEASE
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
        RUNTIME_OUTPUT_DIRECTORY_RELEASE
            "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
)

install(
    TARGETS qros_latency
    LIBRARY DESTINATION cpp_quant_engine
    RUNTIME DESTINATION cpp_quant_engine
)


# Multivariate probability score with fail-closed calibration gate (research only).
nanobind_add_module(qros_probability multivariate_probability.cpp)
target_link_libraries(qros_probability PRIVATE quant_engine)
target_include_directories(qros_probability PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../include)
target_compile_features(qros_probability PRIVATE cxx_std_20)
set_target_properties(qros_probability PROPERTIES
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
  LIBRARY_OUTPUT_DIRECTORY_RELEASE "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine"
  RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_CURRENT_SOURCE_DIR}/../python/cpp_quant_engine")
install(TARGETS qros_probability LIBRARY DESTINATION cpp_quant_engine RUNTIME DESTINATION cpp_quant_engine)
