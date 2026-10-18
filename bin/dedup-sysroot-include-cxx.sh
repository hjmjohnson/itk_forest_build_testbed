#!/usr/bin/env bash
# Wrapper for CMAKE_CXX_COMPILER (Slicer SuperBuild only, opt-in via SLICER_CXX).
#
# Qt6::PrintSupport's exported CMake config bakes in an INTERFACE_INCLUDE_DIRECTORIES
# entry for CUPS/Iconv that, on this toolchain, equals the active -isysroot's own
# usr/include. CMake then emits that as an explicit `-isystem <sysroot>/usr/include`
# alongside the compiler's own implicit search of the same directory. The duplicate
# entry breaks libc++'s self-referential `__has_include_next(<stddef.h>)` lookup in
# <cstddef>, producing:
#   error: <cstddef> tried including <stddef.h> but didn't find libc++'s <stddef.h>
# on every C++ translation unit that transitively includes a Qt header pulling in
# PrintSupport (PythonQt via QtCore is the first to hit it; CTK's CMakeLists has no
# comparable dedup of its own). Confirmed by reproducing the exact failing compile
# command standalone and removing just this one flag pair.
#
# This wrapper drops that single redundant `-isystem <sysroot>/usr/include` pair
# (matched dynamically against whatever -isysroot the invocation already carries,
# not hardcoded to one SDK version) and execs the real compiler with everything
# else untouched.
set -euo pipefail

real="${REAL_CXX:-}"
if [ -z "${real}" ]; then
  for c in "${CONDA_PREFIX:-}/bin/clang++" "$(command -v clang++ || true)"; do
    [ -n "${c}" ] && [ -x "${c}" ] && { real="${c}"; break; }
  done
fi
[ -n "${real}" ] || { echo "dedup-sysroot-include-cxx.sh: no real clang++ found" >&2; exit 1; }

sysroot=""
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  if [ "${args[i]}" = "-isysroot" ] && [ -n "${args[i+1]:-}" ]; then
    sysroot="${args[i+1]}"
    break
  fi
done

out=()
skip_next=0
for ((i = 0; i < ${#args[@]}; i++)); do
  if [ "${skip_next}" = 1 ]; then skip_next=0; continue; fi
  if [ -n "${sysroot}" ] && [ "${args[i]}" = "-isystem" ] && [ "${args[i+1]:-}" = "${sysroot}/usr/include" ]; then
    skip_next=1
    continue
  fi
  out+=("${args[i]}")
done

exec "${real}" "${out[@]}"
