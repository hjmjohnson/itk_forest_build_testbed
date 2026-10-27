cmake_minimum_required(VERSION 3.16)
project(basic CXX)
set(CMAKE_CXX_STANDARD 17)
add_library(foo STATIC foo.cxx)
