#!/usr/bin/env bash
# Final three-backend FFT comparison: PocketFFT vs Vnl vs FFTW, via ITK's
# ComplexToComplexFFTImageFilter on clinical-sized 3-D images. Builds the bench
# against each forest's ITK (Vnl lives only on main, PocketFFT only on the
# branch, FFTW on both), then runs each backend ONE AT A TIME, >=REPS times,
# on a quiet machine. Aggregated medians make the final metrics table.
#
#   bash bin/run-fft-backends.sh [reps] [sizes...]
set -euo pipefail
BIN_DIR="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "${BIN_DIR}")"
SRC="${BIN_DIR}/fftbench"
REPS="${1:-12}"; shift || true
SIZES=("$@"); [ ${#SIZES[@]} -eq 0 ] && SIZES=(128 256)
POCKET_FOREST="${POCKET_FOREST:-build_forest}"
VNL_FOREST="${VNL_FOREST:-build_forest-itkv6_main}"
ncpu=$( (nproc 2>/dev/null) || sysctl -n hw.ncpu 2>/dev/null || echo 4 )
LOAD_MAX="${LOAD_MAX:-$(awk -v n="${ncpu}" 'BEGIN{printf "%.1f", n*0.3}')}"
LOAD_WAIT="${LOAD_WAIT:-0}"
load1(){ uptime | sed -E 's/.*averages?: *([0-9.]+).*/\1/'; }
gate(){ local w=0 l; while :; do l=$(load1)
  awk -v l="$l" -v m="$LOAD_MAX" 'BEGIN{exit !(l<=m)}' && { echo "  load $l <= $LOAD_MAX OK"; return 0; }
  [ "$w" -ge "$LOAD_WAIT" ] && { echo "  ABORT load $l > $LOAD_MAX (waited ${w}s)" >&2; return 1; }
  echo "  load $l > $LOAD_MAX; waiting ${w}/${LOAD_WAIT}s"; sleep 30; w=$((w+30)); done; }

build_bench(){ # forest -> builds bench against that forest's ITK, echoes exe
  local forest="$1"
  local bdir="${ROOT}/${forest}-fftbench"
  local itk="${ROOT}/${forest}/ITK-build"
  [ -f "${itk}/ITKConfig.cmake" ] || { echo "  ${forest}: ITK not built" >&2; return 1; }
  cmake -S "${SRC}" -B "${bdir}" -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DITK_DIR="${itk}" \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache >/dev/null 2>&1
  cmake --build "${bdir}" >/dev/null 2>&1
  echo "${bdir}/bench-fft-backends"
}

echo "=== FFT backend comparison (host=$(hostname -s), reps=${REPS}) ==="
gate || exit 2
echo "building benches..."
POCKET_BIN=$(build_bench "${POCKET_FOREST}") || true
VNL_BIN=$(build_bench "${VNL_FOREST}") || true
echo "  pocket build: ${POCKET_BIN:-FAILED} ($("${POCKET_BIN}" list 2>/dev/null || true))"
echo "  vnl build:    ${VNL_BIN:-FAILED} ($("${VNL_BIN}" list 2>/dev/null || true))"

for s in "${SIZES[@]}"; do
  echo "---- clinical size ${s}^3 ----"
  # one backend at a time; FFTW measured from BOTH builds as a sanity anchor
  [ -n "${VNL_BIN:-}" ]    && "${VNL_BIN}"    vnl       "$s" "${REPS}"
  [ -n "${POCKET_BIN:-}" ] && "${POCKET_BIN}" pocketfft "$s" "${REPS}"
  [ -n "${POCKET_BIN:-}" ] && "${POCKET_BIN}" fftw      "$s" "${REPS}"
done
