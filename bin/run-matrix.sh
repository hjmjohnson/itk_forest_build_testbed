#!/usr/bin/env bash
# Build every downstream against the for/itk-vxl-master ITK; record PASS/FAIL
# by artifact (not exit code), then run each built target's ctest suite and
# record pass/fail counts as a separate column. Continues past failures.
#   pixi run bash bin/run-matrix.sh            # build + test
#   RUN_CTEST=0 pixi run bash bin/run-matrix.sh   # build-only
#
# Slicer note: Slicer never consumes the system ITK. It always builds a
# dedicated Slicer-vendored ITK branch (hjmjohnson/ITK @ slicer-itk-<...>) via
# -DSlicer_ITK_GIT_TAG=<branch>. See docs/slicer-itk-policy.md.
BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "${BIN_DIR}")"            # repo root = parent of bin/
_forest_dir="build_forest${FOREST_REFERENCE_SUFFIX:+-${FOREST_REFERENCE_SUFFIX}}"
FOREST="${FOREST:-${ROOT}/${_forest_dir}}"  # source checkouts + build trees
export FOREST
LOG_TAG="${FOREST_REFERENCE_SUFFIX:+-${FOREST_REFERENCE_SUFFIX}}"
# Prefer the pixi env's toolchain (cmake/ninja/compilers) over any system one,
# so a bare `bash bin/run-matrix.sh` matches `pixi run` (system cmake 3.26.6 is
# too old for Slicer's >=3.28 requirement).
[ -d "${ROOT}/.pixi/envs/default/bin" ] && PATH="${ROOT}/.pixi/envs/default/bin:$PATH"
ENG="${BIN_DIR}/setup-vxl-downstream-testbed.sh"
TB="${FOREST}"
SUMMARY=""

# --- ctest layer -----------------------------------------------------------
# Tests are expensive; bound each target's wall-clock and allow scope/skip:
#   RUN_CTEST=0             build-only matrix (default: 1, run tests)
#   CTEST_JOBS=N            parallel test jobs (default: ncpu/2, min 2)
#   CTEST_TIMEOUT=S         per-test timeout seconds (default 300)
#   CTEST_TARGET_TIMEOUT=S  overall per-target wall-clock cap (default 1800)
#   CTEST_INCLUDE=regex     only run tests matching it (ctest -R) to scope long suites
RUN_CTEST="${RUN_CTEST:-1}"
_ncpu(){ nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4; }
CTEST_JOBS="${CTEST_JOBS:-$(( $(_ncpu) / 2 ))}"; [ "${CTEST_JOBS}" -lt 2 ] && CTEST_JOBS=2
CTEST_TIMEOUT="${CTEST_TIMEOUT:-300}"
CTEST_TARGET_TIMEOUT="${CTEST_TARGET_TIMEOUT:-1800}"

# Build dir that holds CTestTestfile.cmake for a target (inner build for
# SuperBuilds); empty if no test harness is present.
ctest_dir(){
  local n="$1" d
  case "$n" in
    ITK)         d="${TB}/ITK-build" ;;
    BRAINSTools) d="${TB}/BRAINSTools-build/BRAINSTools-Release-EPRelease-build" ;;
    Slicer)      d="${TB}/Slicer-build/Slicer-build" ;;
    *)           d="${TB}/${n}-build" ;;
  esac
  [ -f "${d}/CTestTestfile.cmake" ] && { echo "${d}"; return; }
  local base="${TB}/${n}-build"; [ "$n" = ITK ] && base="${TB}/ITK-build"
  find "${base}" -maxdepth 4 -name CTestTestfile.cmake -print 2>/dev/null \
    | head -1 | xargs -r dirname
}

# Run the test suite for $1; echo a compact token:
#   T:142/150 (8 of 150 failed) | T:0/0:no-tests | T:skip:no-harness | T:timeout
run_ctest(){
  local n="$1" d log line failed total inc=()
  d="$(ctest_dir "$n")"
  [ -n "$d" ] || { echo "T:skip:no-harness"; return; }
  log="/tmp/ctest-${n}${LOG_TAG}.log"
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

artifact_ok(){
  local n="$1" b="${TB}/${1}-build"
  [ "$n" = ITK ] && b="${TB}/ITK-build"
  case "$n" in
    ITK)       [ -f "${b}/lib/libITKCommon-6.0.a" ] ;;
    elastix)   [ -x "${b}/bin/elastix" ] ;;
    c3d)       find "${b}" -name 'c?d' -o -name 'libConvert3D*' 2>/dev/null | grep -q . ;;
    RTK)       [ -x "${b}/bin/rtkamsterdamshroud" ] ;;
    SimpleITK) find "${b}" -name 'libSimpleITK*' 2>/dev/null | grep -q . ;;
    ANTs)        find "${b}" -name 'antsRegistration' 2>/dev/null | grep -q . ;;
    BRAINSTools) find "${b}" -name 'BRAINSFit' 2>/dev/null | grep -q . ;;
    OpenIGTLink)   find "${b}" -iname 'libOpenIGTLink*' 2>/dev/null | grep -q . ;;
    OpenIGTLinkIO) find "${b}" \( -iname 'libigtlio*' -o -iname 'libOpenIGTLinkIO*' \) 2>/dev/null | grep -q . ;;
    vtkAddon)    find "${b}" -iname 'libvtkAddon-*' 2>/dev/null | grep -q . ;;
    IGSIO)       find "${b}" -iname 'libvtkIGSIO*' 2>/dev/null | grep -q . ;;
    PlusLib)     find "${b}" \( -iname 'libvtkPlus*' -o -iname 'libPlus*' \) 2>/dev/null | grep -q . ;;
    Slicer)      find "${TB}/Slicer-build/Slicer-build" \( -name 'SlicerApp-real' -o -name 'libMRMLCore*' \) 2>/dev/null | grep -q . ;;
    SlicerExtensions) find "${b}" \( -name '*.so' -o -name '*.dylib' \) 2>/dev/null | grep -q . ;;
    *)  # external ITK modules link their lib into the ITK tree, not ${name}-build
        { find "${b}" \( -name '*.a' -o -name '*.dylib' -o -name '*.so' \) 2>/dev/null | grep -q . ; } \
        || find "${TB}/ITK-build/lib" -iname "libitk${n}-6.0.a" 2>/dev/null | grep -q . ;;
  esac
}

build_target(){
  local n="$1" tstat=""
  echo "==================== BUILD ${n} ===================="
  bash "${ENG}" build "${n}" >"/tmp/matrix-${n}${LOG_TAG}.log" 2>&1
  if artifact_ok "${n}"; then
    echo "RESULT ${n}: build PASS"
    if [ "${RUN_CTEST}" = 1 ]; then
      echo "-------------------- CTEST ${n} --------------------"
      tstat="$(run_ctest "${n}")"
      echo "RESULT ${n}: ${tstat}  (/tmp/ctest-${n}${LOG_TAG}.log)"
    fi
    SUMMARY="${SUMMARY}$(printf 'PASS  %-20s %s' "${n}" "${tstat}")"$'\n'
  else
    SUMMARY="${SUMMARY}$(printf 'FAIL  %-20s %s' "${n}" '(build failed)')"$'\n'
    echo "RESULT ${n}: build FAIL  (/tmp/matrix-${n}${LOG_TAG}.log)"
    grep -iE 'error:|CMake Error|library not found|No such module|undefined sym' "/tmp/matrix-${n}${LOG_TAG}.log" | head -3
  fi
}

# DEFERRED — known non-vxl failures, excluded until fixed (see docs/DEFERRED-FAILURES.md):
#   TubeTK c3d BioCell HASI Shape SkullStrip : need their own module/data deps
#   Ultrasound          : extra ITK COMPILE_DEPENDS / clFFT not resolved
#   LesionSizingToolkit : missing itkCannyEdgeDetectionRecursiveGaussianImageFilter.h,
#                         itkLandmarksReader.h (needs more ITK modules enabled)
#   SphinxExamples      : ExternalData test-data fetch (not a build/link issue)
# None are vxl/vnl-related. Re-include a target here only after its cause is fixed.
TARGETS=(ITK elastix SimpleITK RTK Cleaver
         PerformanceBenchmarking SimpleITKFilters
         TractographyTRX VkFFTBackend ANTs BRAINSTools
         OpenIGTLink OpenIGTLinkIO vtkAddon IGSIO PlusLib
         Slicer SlicerExtensions)

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
