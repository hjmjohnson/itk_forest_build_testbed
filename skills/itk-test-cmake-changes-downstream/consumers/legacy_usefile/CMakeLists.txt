# Idiom: legacy ITKv5 UseITK include + ITK_LIBRARIES.
# Real-world matches: c3d, elastix, LesionSizingToolkit.
cmake_minimum_required(VERSION 3.16.3)
project(legacy_usefile CXX)
include(${CMAKE_CURRENT_SOURCE_DIR}/../common.cmake)
find_package(ITK REQUIRED)
include(${ITK_USE_FILE})
add_executable(app ${PROBE_SRC})
target_link_libraries(app ${ITK_LIBRARIES})
