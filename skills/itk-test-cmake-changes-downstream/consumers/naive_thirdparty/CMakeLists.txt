# Canary: a consumer that references the upstream third-party imported target
# (e.g. ZLIB::ZLIB) WITHOUT its own find_package, relying on find_package(ITK)
# to have re-discovered it. This is the consumer that breaks when ITK stops
# re-running find_package(<dep>) in its exported config. Expected to FAIL for a
# correctly-written consumer's sake is fine — the point is to detect *whether*
# ITK still provides the transitive target, and to flag build-tree vs
# install-tree divergence.
cmake_minimum_required(VERSION 3.16.3)
project(naive_thirdparty CXX)
include(${CMAKE_CURRENT_SOURCE_DIR}/../common.cmake)
find_package(ITK REQUIRED)
add_executable(app ${PROBE_SRC})
target_link_libraries(app ${ITK_MODULE_TARGET} ${THIRDPARTY_TARGET})
