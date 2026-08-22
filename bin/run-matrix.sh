#!/usr/bin/env bash
# Build every downstream against the ITK ref under test; record PASS/FAIL
# by artifact (not exit code), then run each built target's ctest suite and
# record pass/fail counts as a separate column. Continues past failures.
#   pixi run bash bin/run-matrix.sh            # build + test
#   RUN_CTEST=0 pixi run bash bin/run-matrix.sh   # build-only
#   bin/run-matrix.sh --list-targets|--list-deferred|--check-artifact <X>|--ctest-dir <X>|--run-ctest <X>
#
# Slicer note: Slicer never consumes the system ITK. It always builds a
# dedicated Slicer-vendored ITK branch (hjmjohnson/ITK @ slicer-itk-<...>) via
# -DSlicer_ITK_GIT_TAG=<branch>. See docs/slicer-itk-policy.md.
BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "${BIN_DIR}")"            # repo root = parent of bin/
ENG="${BIN_DIR}/setup-itk-downstream-testbed.sh"
# Artifact filenames and the conda env layout differ per platform; platform.sh
# is the single authority for both (see docs/windows.md).
. "${BIN_DIR}/platform.sh"
# The engine is the single authority on the forest name; ask it rather than
# recomputing the composition here and risking drift.
# No `set -e` here (the matrix continues past build failures), so an engine that
# dies must be caught explicitly: an empty FOREST would root LOGDIR at "/logs"
# and build the whole matrix at "/".
FOREST="${FOREST:-$(bash "${ENG}" --print-forest)}" || exit 1
[ -n "${FOREST}" ] || { echo "run-matrix: engine could not resolve the forest name" >&2; exit 1; }
export FOREST
LOG_TAG="${FOREST_REFERENCE_SUFFIX:+-${FOREST_REFERENCE_SUFFIX}}"
# Put the pixi env's cmake/ninja ahead of any system one (system cmake 3.26.6 is
# too old for Slicer's >=3.28 requirement). This is NOT equivalent to `pixi run`:
# the compilers ($CC/$CXX) and the ccache hash policy come from the activation
# env, not from PATH. Run under `pixi run`; the engine enforces it.
# A conda env's executables are in bin/ on Unix but in the env root +
# Library/bin + Scripts on Windows, so ask platform.sh rather than hardcoding
# bin/ (which simply does not exist on win-64 and made this a silent no-op).
# upath: $PATH is colon-separated, so entries must be shell form, not "C:/...".
while IFS= read -r _d; do
  [ -d "${_d}" ] && PATH="$(upath "${_d}"):$PATH"
done < <(pixi_env_bindirs "${ROOT}/.pixi/envs/default")
TB="${FOREST}"
LOGDIR="${FOREST}/logs"
case "${1:-}" in
  --list-targets|--list-deferred|--check-artifact|--ctest-dir) : ;;
  *) mkdir -p "${LOGDIR}" ;;
esac
SUMMARY=""

# --- ctest layer -----------------------------------------------------------
# Tests are expensive; bound each target's wall-clock and allow scope/skip:
#   RUN_CTEST=0             build-only matrix (default: 1, run tests)
#   CTEST_JOBS=N            parallel test jobs (default: ncpu/2, min 2)
#   CTEST_TIMEOUT=S         per-test timeout seconds (default 300)
#   CTEST_TARGET_TIMEOUT=S  overall per-target wall-clock cap (default 1800)
#   CTEST_INCLUDE=regex     only run tests matching it (ctest -R) to scope long suites
RUN_CTEST="${RUN_CTEST:-1}"
# Slicer extension self-tests stay off independently of RUN_CTEST: the extension
# dashboard driver's own ctest_test launches Slicer.app per extension, and a crash
# there leaves a modal macOS dialog that blocks an unattended build. The engine
# reads SLICER_EXT_RUN_TESTS, but the per-extension args files are regenerated
# during the BUILD, so the flag must be live in this process's environment --
# not only inside configure_one. SLICER_EXT_RUN_TESTS=1 opts back in (attended).
export SLICER_EXT_RUN_TESTS="${SLICER_EXT_RUN_TESTS:-0}"
if [ "${SLICER_EXT_RUN_TESTS}" = 1 ]; then
  export run_extension_ctest_with_test=TRUE
else
  export run_extension_ctest_with_test=FALSE
fi
export run_extension_ctest_with_packages="${run_extension_ctest_with_packages:-FALSE}"
export run_extension_ctest_submit=FALSE
_ncpu(){ nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4; }
CTEST_JOBS="${CTEST_JOBS:-$(( $(_ncpu) / 2 ))}"; [ "${CTEST_JOBS}" -lt 2 ] && CTEST_JOBS=2
CTEST_TIMEOUT="${CTEST_TIMEOUT:-300}"
CTEST_TARGET_TIMEOUT="${CTEST_TARGET_TIMEOUT:-1800}"

# Build tree for a target: nested layout (<name>/build, mirrors the engine's
# build_dir()) with a fallback to the legacy flat <name>-build.
bdir(){
  local d="${TB}/${1}/build"
  [ -d "${d}" ] || { [ -d "${TB}/${1}-build" ] && d="${TB}/${1}-build"; }
  echo "${d}"
}

# Build dir that holds CTestTestfile.cmake for a target (inner build for
# SuperBuilds); empty if no test harness is present.
ctest_dir(){
  local n="$1" d
  case "$n" in
    BRAINSTools) d="$(bdir BRAINSTools)/BRAINSTools-Release-EPRelease-build" ;;
    Slicer)      d="$(bdir Slicer)/Slicer-build" ;;
    *)           d="$(bdir "$n")" ;;
  esac
  [ -f "${d}/CTestTestfile.cmake" ] && { echo "${d}"; return; }
  find "$(bdir "$n")" -maxdepth 4 -name CTestTestfile.cmake -print 2>/dev/null \
    | head -1 | xargs -r dirname
}

# Run the test suite for $1; echo a compact token:
#   T:142/150 (8 of 150 failed) | T:0/0:no-tests | T:skip:no-harness | T:timeout
run_ctest(){
  local n="$1" d log line failed total inc=()
  d="$(ctest_dir "$n")"
  [ -n "$d" ] || { echo "T:skip:no-harness"; return; }
  log="${LOGDIR}/ctest-${n}${LOG_TAG}.log"
  [ -n "${CTEST_INCLUDE:-}" ] && inc=(-R "${CTEST_INCLUDE}")
  timeout "${CTEST_TARGET_TIMEOUT}" \
    ctest --test-dir "$d" -j"${CTEST_JOBS}" --timeout "${CTEST_TIMEOUT}" \
      --output-on-failure "${inc[@]}" >"$log" 2>&1
  [ $? -eq 124 ] && { echo "T:timeout"; return; }
  line="$(grep -E 'tests passed,.*tests failed out of' "$log" | tail -1)"
  if [ -z "$line" ]; then
    grep -qE 'No tests were found' "$log" && { echo "T:0/0:no-tests"; return; }
    echo "T:unknown"; return
  fi
  failed="$(echo "$line" | sed -E 's/.* ([0-9]+) tests failed.*/\1/')"
  total="$(echo "$line" | sed -E 's/.* out of ([0-9]+).*/\1/')"
  echo "T:$((total - failed))/${total}"
}

# Artifact predicates. The FILENAME SHAPES are platform-specific (MSVC emits
# Foo.lib/Foo.dll and foo.exe, with no "lib" prefix, where Unix emits
# libFoo.a/libFoo.so|dylib and foo), so they come from platform.sh and only the
# per-target STEMS live here. Before this split every check below was
# Unix-shaped and a fully-built Windows tree scored as a build FAILURE --
# which, for ITK, aborted the whole matrix on its first target.
_find_any(){                    # <dir> <glob>... -> 0 if any file matches
  local d="$1"; shift
  [ -d "$d" ] || return 1
  local g; local -a args=()
  for g in "$@"; do [ ${#args[@]} -gt 0 ] && args+=(-o); args+=(-iname "$g"); done
  find "$d" \( "${args[@]}" \) 2>/dev/null | grep -q .
}
# Read the globs into an array rather than splitting $(...): unquoted expansion
# would let the shell glob them against the CWD before find ever sees them.
has_lib(){                      # <dir> <stem-without-lib-prefix>
  local g; local -a gl=()
  while IFS= read -r g; do gl+=("$g"); done < <(lib_globs "$2")
  _find_any "$1" "${gl[@]}"; }
has_any_lib(){                  # <dir>
  local g; local -a gl=()
  while IFS= read -r g; do gl+=("$g"); done < <(any_lib_globs)
  _find_any "$1" "${gl[@]}"; }
has_exe(){ _find_any "$1" "${2}${EXE_SUFFIX}"; }   # <dir> <name-without-suffix>

artifact_ok(){
  local n="$1" b
  b="$(bdir "$n")"
  case "$n" in
    ITK)       has_lib "${b}/lib" 'ITKCommon-*' ;;  # version-agnostic (6.0, 5.4, ...)
    elastix)   has_exe "${b}/bin" elastix ;;
    c3d)       has_exe "${b}" 'c?d' || has_lib "${b}" 'Convert3D*' ;;
    RTK)       has_exe "${b}/bin" rtkamsterdamshroud ;;
    SimpleITK) has_lib "${b}" 'SimpleITK*' ;;
    ANTs)        has_exe "${b}" antsRegistration ;;
    BRAINSTools) has_exe "${b}" BRAINSFit ;;
    OpenIGTLink)   has_lib "${b}" 'OpenIGTLink*' ;;
    OpenIGTLinkIO) has_lib "${b}" 'igtlio*' || has_lib "${b}" 'OpenIGTLinkIO*' ;;
    vtkAddon)    has_lib "${b}" 'vtkAddon*' ;;
    IGSIO)       has_lib "${b}" 'vtkIGSIO*' ;;
    PlusLib)     has_lib "${b}" 'vtkPlus*' || has_lib "${b}" 'Plus*' ;;
    Slicer)      has_exe "$(bdir Slicer)/Slicer-build" 'SlicerApp-real' \
                 || has_lib "$(bdir Slicer)/Slicer-build" 'MRMLCore*' ;;
    SlicerExtensions) has_any_lib "${b}" ;;
    *)  # external ITK modules link their lib into the ITK tree, not their own
        has_any_lib "${b}" || has_lib "$(bdir ITK)/lib" "itk${n}-*" ;;
  esac
}
build_target(){
  local n="$1" tstat=""
  echo "==================== BUILD ${n} ===================="
  local _t0 _el; _t0=$(date +%s)
  bash "${ENG}" build "${n}" >"${LOGDIR}/matrix-${n}${LOG_TAG}.log" 2>&1
  _el=$(( $(date +%s) - _t0 ))
  # Verify tests actually stayed off for extensions -- the args files bake
  # RUN_CTEST_TEST at their own configure time, so an env slip re-enables the
  # Slicer.app-launching test phase silently. Assert by artifact, not intent.
  if [ "${n}" = SlicerExtensions ] && [ "${RUN_CTEST}" = 0 ]; then
    local _on; _on="$(grep -l 'RUN_CTEST_TEST "TRUE"' "${FOREST}/SlicerExtensions/build/"*-test-command-args.cmake 2>/dev/null | wc -l | tr -d ' ')"
    [ "${_on:-0}" != 0 ] && echo "WARN ${n}: ${_on} extension(s) still have tests ENABLED despite RUN_CTEST=0 (Slicer.app may launch)"
  fi
  if artifact_ok "${n}"; then
    echo "RESULT ${n}: build PASS  (${_el}s)"
    if [ "${RUN_CTEST}" = 1 ]; then
      echo "-------------------- CTEST ${n} --------------------"
      tstat="$(run_ctest "${n}")"
      echo "RESULT ${n}: ${tstat}  (${LOGDIR}/ctest-${n}${LOG_TAG}.log)"
    fi
    SUMMARY="${SUMMARY}$(printf 'PASS  %-20s %7ss  %s' "${n}" "${_el}" "${tstat}")"$'\n'
  else
    SUMMARY="${SUMMARY}$(printf 'FAIL  %-20s %7ss  %s' "${n}" "${_el}" '(build failed)')"$'\n'
    echo "RESULT ${n}: build FAIL  (${_el}s)  (${LOGDIR}/matrix-${n}${LOG_TAG}.log)"
    grep -iE 'error:|CMake Error|library not found|No such module|undefined sym' "${LOGDIR}/matrix-${n}${LOG_TAG}.log" | head -3
  fi
}

# DEFERRED — known pre-existing failures unrelated to the ITK ref under test,
# excluded until fixed (see docs/DEFERRED-FAILURES.md):
#   TubeTK c3d BioCell HASI Shape SkullStrip : need their own module/data deps
#   Ultrasound          : extra ITK COMPILE_DEPENDS / clFFT not resolved
#   LesionSizingToolkit : missing itkCannyEdgeDetectionRecursiveGaussianImageFilter.h,
#                         itkLandmarksReader.h (needs more ITK modules enabled)
#   SphinxExamples      : ExternalData test-data fetch (not a build/link issue)
# None are caused by the ITK ref under test. Re-include a target only after its cause is fixed.
# Slicer (and its full rendering+Qt VTK) precedes the VTK consumers
# (OpenIGTLinkIO/vtkAddon/IGSIO/PlusLib), which need that VTK via vtk_dir().
TARGETS=(ITK elastix SimpleITK RTK Cleaver
         PerformanceBenchmarking SimpleITKFilters
         TractographyTRX VkFFTBackend ANTs BRAINSTools
         OpenIGTLink Slicer SlicerExtensions
         OpenIGTLinkIO vtkAddon IGSIO PlusLib)

# QT_FREE_TARGETS — the subset that needs no Qt6. Slicer and SlicerExtensions
# link Qt directly; OpenIGTLinkIO/vtkAddon/IGSIO/PlusLib need vtk_dir(), whose
# only providers are the forest's Qt-enabled VTK or Slicer's VTK, and both go
# through qt6_or_die. Useful on a node with no usable Qt6 kit:
#   MATRIX_TARGETS="$(bash bin/run-matrix.sh --list-qt-free)" pixi run bash bin/run-matrix.sh
QT_FREE_TARGETS=(ITK elastix SimpleITK RTK Cleaver
                 PerformanceBenchmarking SimpleITKFilters
                 TractographyTRX VkFFTBackend ANTs BRAINSTools
                 OpenIGTLink)

# MATRIX_TARGETS (space-separated) overrides the built-in list, so a scoped
# sweep is a normal matrix run -- same artifact scoring, same logs, same
# summary -- rather than an ad-hoc loop that re-implements them.
[ -n "${MATRIX_TARGETS:-}" ] && read -r -a TARGETS <<<"${MATRIX_TARGETS}"

# Deferred targets (see docs/DEFERRED-FAILURES.md) as machine-readable rows.
DEFERRED_TARGETS=(
  $'TubeTK\tneeds its own module/data deps'
  $'c3d\tneeds its own module/data deps'
  $'BioCell\tneeds its own module/data deps'
  $'HASI\tneeds its own module/data deps'
  $'Shape\tneeds its own module/data deps'
  $'SkullStrip\tneeds its own module/data deps'
  $'Ultrasound\textra ITK COMPILE_DEPENDS / clFFT not resolved'
  $'LesionSizingToolkit\tneeds more ITK modules enabled (missing headers)'
  $'SphinxExamples\tExternalData test-data fetch failure'
)

# Query/action modes for tooling (forest_tui); default no-flag behavior unchanged.
case "${1:-}" in
  --list-targets)   printf '%s\n' "${TARGETS[@]}"; exit 0 ;;
  --list-deferred)  printf '%s\n' "${DEFERRED_TARGETS[@]}"; exit 0 ;;
  --list-qt-free)   printf '%s\n' "${QT_FREE_TARGETS[@]}"; exit 0 ;;
  --check-artifact) artifact_ok "${2:?usage: --check-artifact <target>}"; exit $? ;;
  --ctest-dir)      ctest_dir "${2:?usage: --ctest-dir <target>}"; exit 0 ;;
  --run-ctest)      run_ctest "${2:?usage: --run-ctest <target>}"; exit 0 ;;
esac

for t in "${TARGETS[@]}"; do
  # VkFFTBackend is GPU-gated: build with CUDA/Metal/OpenCL where available,
  # skip (not fail) on hosts with no GPU backend.
  if [ "$t" = VkFFTBackend ] && [ -z "$(bash "${ENG}" vkfft-backend 2>/dev/null)" ]; then
    SUMMARY="${SUMMARY}$(printf 'SKIP  %-20s %s' "${t}" '(no GPU backend)')"$'\n'
    echo "RESULT ${t}: SKIP (no CUDA/Metal/OpenCL backend)"; continue
  fi
  if [ "$t" = ITK ] || [ -d "${TB}/${t}" ]; then build_target "$t"
  else SUMMARY="${SUMMARY}SKIP  ${t}"$'\n'; echo "RESULT ${t}: SKIP (not checked out)"; fi
  if [ "$t" = ITK ] && ! artifact_ok ITK; then echo "ITK FAILED — aborting"; break; fi
done

echo; echo "==================== MATRIX ===================="
printf '%s' "${SUMMARY}"
