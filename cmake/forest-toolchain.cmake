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
