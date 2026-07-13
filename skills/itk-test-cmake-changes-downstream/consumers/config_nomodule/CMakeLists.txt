# Idiom: explicit CONFIG mode (NO_MODULE) + UseITK.
# Real-world match: IGSIO (find_package(ITK REQUIRED NO_MODULE)).
cmake_minimum_required(VERSION 3.16.3)
project(config_nomodule CXX)
include(${CMAKE_CURRENT_SOURCE_DIR}/../common.cmake)
find_package(ITK REQUIRED NO_MODULE)
include(${ITK_USE_FILE})
add_executable(app ${PROBE_SRC})
target_link_libraries(app ${ITK_LIBRARIES})
