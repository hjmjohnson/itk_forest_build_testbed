# forest-toolchain.cmake
#
# Cross-cutting settings that MUST reach SuperBuild inner ExternalProjects. A
# top-level -D cache variable stops at the outer project; a toolchain file is
# re-read at every nesting level (when CMAKE_TOOLCHAIN_FILE is forwarded), so
# settings here apply to inner EPs too — where -DCMAKE_IGNORE_PREFIX_PATH and
# -DCMAKE_BUILD_RPATH on the outer configure do not.
#
# Sets no CMAKE_SYSTEM_NAME/PROCESSOR, so it never triggers cross-compile mode.

# 1. Keep every find_package/find_library off the Homebrew tree. On arm64 macOS
#    CMake puts /opt/homebrew on the default system prefix path; it ABI-mismatches
#    the conda-forge stack and leaks libintl/freetype/fontconfig/X11 into inner
#    EPs (e.g. Slicer's bundled CPython links Homebrew libintl's _libintl_*
#    symbols but omits -lintl -> undefined symbols).
if(NOT "/opt/homebrew" IN_LIST CMAKE_IGNORE_PREFIX_PATH)
  list(APPEND CMAKE_IGNORE_PREFIX_PATH /opt/homebrew)
endif()

# 2. Bake the conda libdir as a build rpath so conda libc++/fftw resolve at build
#    and run time in inner EPs too (complements the LDFLAGS -rpath export).
if(DEFINED ENV{CONDA_PREFIX} AND NOT "$ENV{CONDA_PREFIX}/lib" IN_LIST CMAKE_BUILD_RPATH)
  list(APPEND CMAKE_BUILD_RPATH "$ENV{CONDA_PREFIX}/lib")
endif()

# 3. Force CMake's FindIconv to the conda libiconv. The conda compiler's default
#    include has conda's GNU iconv.h, which macro-renames iconv->libiconv_*; the
#    matching symbols live in conda's libiconv, not the macOS SDK libiconv.tbd
#    (plain _iconv) that FindIconv would otherwise pick. Without this, GDCM's
#    mec_mr3_io.c (and any iconv user) fails to link with undefined _libiconv_*.
if(APPLE AND DEFINED ENV{CONDA_PREFIX} AND EXISTS "$ENV{CONDA_PREFIX}/lib/libiconv.dylib")
  set(Iconv_INCLUDE_DIR "$ENV{CONDA_PREFIX}/include" CACHE PATH "conda iconv (matches compiler default header)" FORCE)
  set(Iconv_LIBRARY "$ENV{CONDA_PREFIX}/lib/libiconv.dylib" CACHE FILEPATH "conda iconv (has libiconv_* symbols)" FORCE)
endif()

# 4. Linux: conda binutils (new-dtags) does not search -rpath when resolving a
#    shared library's own NEEDED entries at link time, so executables linking a
#    lib with PRIVATE shared deps (e.g. ITK's itkTestDriver vs ITKTestKernel's
#    IO factories) fail with "needed by ... not found". Point -rpath-link at
#    the consuming project's own lib dir.
if(UNIX AND NOT APPLE)
  # Own lib dir plus sibling SuperBuild EP lib dirs (Slicer layout: the EPs
  # are peers under the SuperBuild root; nonexistent dirs are harmless).
  set(_forest_rpl " -Wl,-rpath-link,${CMAKE_BINARY_DIR}/lib")
  foreach(_forest_dep ITK-build/lib VTK-build/lib CTK-build/CTK-build/lib
                      DCMTK-build/lib tbb-install/lib LibArchive-install/lib
                      SlicerExecutionModel-build/lib)
    string(APPEND _forest_rpl " -Wl,-rpath-link,${CMAKE_BINARY_DIR}/../${_forest_dep}")
  endforeach()
  string(APPEND CMAKE_EXE_LINKER_FLAGS_INIT "${_forest_rpl}")
  string(APPEND CMAKE_SHARED_LINKER_FLAGS_INIT "${_forest_rpl}")
  string(APPEND CMAKE_MODULE_LINKER_FLAGS_INIT "${_forest_rpl}")
  unset(_forest_rpl)
endif()

# 5. Linux: the conda compiler's default iconv.h macro-renames iconv->libiconv_*
#    but only some libraries (e.g. GDCM's MSFF) record the dependency; append
#    conda libiconv so those symbols resolve on every executable link.
if(UNIX AND NOT APPLE AND DEFINED ENV{CONDA_PREFIX} AND EXISTS "$ENV{CONDA_PREFIX}/lib/libiconv.so")
  string(APPEND CMAKE_C_STANDARD_LIBRARIES_INIT " $ENV{CONDA_PREFIX}/lib/libiconv.so")
  string(APPEND CMAKE_CXX_STANDARD_LIBRARIES_INIT " $ENV{CONDA_PREFIX}/lib/libiconv.so")
endif()

# 6. Linux: shared libs built against an under-linked static zlib (e.g. the
#    slicer-itk branch's IO modules vs Slicer's zlib EP) leave plain zlib
#    symbols undefined; the conda libz resolves them at executable link.
if(UNIX AND NOT APPLE AND DEFINED ENV{CONDA_PREFIX} AND EXISTS "$ENV{CONDA_PREFIX}/lib/libz.so")
  string(APPEND CMAKE_C_STANDARD_LIBRARIES_INIT " $ENV{CONDA_PREFIX}/lib/libz.so")
  string(APPEND CMAKE_CXX_STANDARD_LIBRARIES_INIT " $ENV{CONDA_PREFIX}/lib/libz.so")
endif()
