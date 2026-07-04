# Drop-in for ITK MorphologicalContourInterpolation/test/CMakeLists.txt.
# Append after the DSCTest() invocations. Gated so a normal `ctest` run (no
# resource-spec file) is unaffected -- RESOURCE_GROUPS without a spec file is a
# hard CTest error, so the labels must stay opt-in behind ITK_CTEST_MEMORY_BUDGET.
#
# Measured peak RSS on the full-resolution DSC cases is ~0.7 GB each (not >3 GB),
# so the CI SIGABRT is aggregate memory under `ctest -j3`, not one giant test.
# Reserving ~1 GB-slot per case lets CTest cap how many co-run against the
# runner's RAM budget instead of forcing any single test to run alone.

if(ITK_CTEST_MEMORY_BUDGET)
  foreach(
    _mci_heavy
    itkMCI_DSC_case_2_binary
    itkMCI_DSC_case_2_labels
    itkMCI_DSC_case_10_binary
    itkMCI_DSC_case_10_labels
  )
    if(TEST ${_mci_heavy})
      set_property(TEST ${_mci_heavy} APPEND PROPERTY RESOURCE_GROUPS "mem:1")
    endif()
  endforeach()
endif()
