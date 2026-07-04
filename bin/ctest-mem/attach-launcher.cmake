# Attach the peak-RSS launcher to every registered test for a profiling pass.
# Include at the END of the top-level CMakeLists (after all add_test/itk_add_test):
#     include(/path/to/bin/ctest-mem/attach-launcher.cmake)
# and configure with -DITK_PROFILE_TEST_RSS=ON.
#
# Requires CMake >= 3.29 for the per-test TEST_LAUNCHER property.
# Writes one "<name>,<peakMB>,<exit>" line per test to ${ITK_RSS_CSV}.

if(ITK_PROFILE_TEST_RSS)
  if(CMAKE_VERSION VERSION_LESS 3.29)
    message(FATAL_ERROR "ITK_PROFILE_TEST_RSS needs CMake >= 3.29 (TEST_LAUNCHER).")
  endif()

  set(ITK_RSS_CSV "${CMAKE_BINARY_DIR}/ctest-rss.csv"
      CACHE FILEPATH "Peak-RSS profiling output")
  set(_rss_launcher "${CMAKE_CURRENT_LIST_DIR}/measure-test-rss.sh")

  # Collect tests across the whole directory tree (TESTS is per-directory).
  function(_rss_collect_tests dir out_var)
    get_property(_here DIRECTORY "${dir}" PROPERTY TESTS)
    get_property(_subs DIRECTORY "${dir}" PROPERTY SUBDIRECTORIES)
    foreach(_s IN LISTS _subs)
      _rss_collect_tests("${_s}" _child)
      list(APPEND _here ${_child})
    endforeach()
    set(${out_var} "${_here}" PARENT_SCOPE)
  endfunction()

  _rss_collect_tests("${CMAKE_SOURCE_DIR}" _all_tests)
  list(REMOVE_DUPLICATES _all_tests)
  foreach(_t IN LISTS _all_tests)
    set_property(TEST ${_t} PROPERTY TEST_LAUNCHER
                 "${CMAKE_COMMAND};-E;env;RSS_CSV=${ITK_RSS_CSV};RSS_NAME=${_t};${_rss_launcher}")
  endforeach()
  list(LENGTH _all_tests _n)
  message(STATUS "ITK_PROFILE_TEST_RSS: wrapped ${_n} tests -> ${ITK_RSS_CSV}")
endif()
