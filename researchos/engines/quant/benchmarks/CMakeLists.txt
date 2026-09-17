add_executable(quant_engine_bench benchmark_main.cpp)
target_link_libraries(quant_engine_bench PRIVATE quant_engine)
target_include_directories(quant_engine_bench PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../include)

add_executable(quant_engine_ci_smoke ci_smoke.cpp)
target_link_libraries(quant_engine_ci_smoke PRIVATE quant_engine)
target_include_directories(quant_engine_ci_smoke PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../include)
