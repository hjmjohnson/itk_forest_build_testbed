#!/usr/bin/env bash
# Build every downstream against the for/itk-vxl-master ITK; record PASS/FAIL
# by artifact (not exit code). Continues past failures.
#   pixi run bash bin/run-matrix.sh
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
    Slicer)      find "${TB}/Slicer-build/Slicer-build" \( -name 'SlicerApp-real' -o -name 'libMRMLCore*' \) 2>/dev/null | grep -q . ;;
    SlicerExtensions) find "${b}" \( -name '*.so' -o -name '*.dylib' \) 2>/dev/null | grep -q . ;;
    *)  # external ITK modules link their lib into the ITK tree, not ${name}-build
        { find "${b}" \( -name '*.a' -o -name '*.dylib' -o -name '*.so' \) 2>/dev/null | grep -q . ; } \
        || find "${TB}/ITK-build/lib" -iname "libitk${n}-6.0.a" 2>/dev/null | grep -q . ;;
  esac
}

build_target(){
  local n="$1"
  echo "==================== BUILD ${n} ===================="
  bash "${ENG}" build "${n}" >"/tmp/matrix-${n}${LOG_TAG}.log" 2>&1
  if artifact_ok "${n}"; then
    SUMMARY="${SUMMARY}PASS  ${n}"$'\n'; echo "RESULT ${n}: PASS"
  else
    SUMMARY="${SUMMARY}FAIL  ${n}"$'\n'; echo "RESULT ${n}: FAIL  (/tmp/matrix-${n}${LOG_TAG}.log)"
    grep -iE 'error:|CMake Error|library not found|No such module|undefined sym' "/tmp/matrix-${n}${LOG_TAG}.log" | head -3
  fi
}

# DEFERRED — known non-vxl failures, excluded until fixed (see DEFERRED-FAILURES.md):
#   TubeTK c3d BioCell HASI Shape SkullStrip : need their own module/data deps
#   Ultrasound          : extra ITK COMPILE_DEPENDS / clFFT not resolved
#   LesionSizingToolkit : missing itkCannyEdgeDetectionRecursiveGaussianImageFilter.h,
#                         itkLandmarksReader.h (needs more ITK modules enabled)
#   SphinxExamples      : ExternalData test-data fetch (not a build/link issue)
# None are vxl/vnl-related. Re-include a target here only after its cause is fixed.
TARGETS=(ITK elastix SimpleITK RTK Cleaver
         PerformanceBenchmarking SimpleITKFilters
         TractographyTRX VkFFTBackend ANTs BRAINSTools
         Slicer SlicerExtensions)

for t in "${TARGETS[@]}"; do
  if [ "$t" = ITK ] || [ -d "${TB}/${t}" ]; then build_target "$t"
  else SUMMARY="${SUMMARY}SKIP  ${t}"$'\n'; echo "RESULT ${t}: SKIP (not checked out)"; fi
  if [ "$t" = ITK ] && ! artifact_ok ITK; then echo "ITK FAILED — aborting"; break; fi
done

echo; echo "==================== MATRIX ===================="
printf '%s' "${SUMMARY}"
