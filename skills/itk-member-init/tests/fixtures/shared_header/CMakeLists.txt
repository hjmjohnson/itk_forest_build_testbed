cmake_minimum_required(VERSION 3.16)
project(shared_header CXX)
set(CMAKE_CXX_STANDARD 17)
add_library(foo STATIC a.cxx b.cxx)
