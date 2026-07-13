# Idiom: most-modern, links the specific ITK module interface target directly.
# Exercises that the exported target carries the dependency's usage
# requirements (include dirs + link) with no variable plumbing.
cmake_minimum_required(VERSION 3.16.3)
project(direct_target CXX)
include(${CMAKE_CURRENT_SOURCE_DIR}/../common.cmake)
find_package(ITK REQUIRED)
add_executable(app ${PROBE_SRC})
target_link_libraries(app ${ITK_MODULE_TARGET})
