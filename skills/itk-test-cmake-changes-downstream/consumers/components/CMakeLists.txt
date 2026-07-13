# Idiom: version + COMPONENTS request (loads only the named module subtree).
# Real-world matches: elastix (find_package(ITK 5.4.1 REQUIRED COMPONENTS ...)),
# RTK (find_package(ITK 5.1 REQUIRED)).
cmake_minimum_required(VERSION 3.16.3)
project(components CXX)
include(${CMAKE_CURRENT_SOURCE_DIR}/../common.cmake)
find_package(ITK REQUIRED COMPONENTS ${FIND_COMPONENTS})
include(${ITK_USE_FILE})
add_executable(app ${PROBE_SRC})
target_link_libraries(app ${ITK_LIBRARIES})
