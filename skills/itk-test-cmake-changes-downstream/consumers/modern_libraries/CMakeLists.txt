# Idiom: modern target-based, no UseITK.
# Real-world matches: BioCell, Cleaver, HASI, RTK, Shape, most ITK remote modules.
cmake_minimum_required(VERSION 3.16.3)
project(modern_libraries CXX)
include(${CMAKE_CURRENT_SOURCE_DIR}/../common.cmake)
find_package(ITK REQUIRED)
add_executable(app ${PROBE_SRC})
target_link_libraries(app ${ITK_LIBRARIES})
