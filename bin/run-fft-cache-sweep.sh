#!/usr/bin/env bash
# Sweep POCKETFFT_CACHE_SIZE to pick the ITK default. Reports ns/transform for:
#   single-size (N3/N4 histogram FFT, fixed len 512) -> lookup overhead of a big cache
#   multi-size  (general pipelines) -> thrashing when cache < #distinct sizes
set -euo pipefail
BIN_DIR="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "${BIN_DIR}")"
OUT="${ROOT}/.devlocal/fft-bench"; mkdir -p "${OUT}"
INC=$(find "${ROOT}"/build_forest*/ITK/Modules/Filtering/FFT/include -name pocketfft_hdronly.h 2>/dev/null | head -1); INC="${INC%/*}"
[ -f "${INC}/pocketfft_hdronly.h" ] || { echo "pocketfft header not found" >&2; exit 1; }
CXX="${CXX:-$(command -v c++ || command -v clang++ || command -v g++)}"
REPS="${REPS:-200000}"
SINGLE="${SINGLE:-512}"                 # N3/N4 histogram FFT length (200 bins -> 2^9)
MULTI="${MULTI:-512,200,256,128,640,96,360,1024}"  # mixed image-domain sizes

echo "=== POCKETFFT_CACHE_SIZE sweep (host=$(hostname -s), CXX=${CXX##*/}) ==="
for sizes in "${SINGLE}" "${MULTI}"; do
  nd=$(awk -F, '{print NF}' <<<"${sizes}")
  echo "-- workload: ${nd} distinct length(s) [${sizes}], reps=${REPS}"
  for cs in 0 1 2 4 8 16 32 64; do
    bin="${OUT}/sweep_cs${cs}"
    "${CXX}" -O3 -std=c++17 -DPOCKETFFT_CACHE_SIZE="${cs}" -I"${INC}" \
      "${BIN_DIR}/fft-cache-sweep-probe.cxx" -o "${bin}" -lpthread 2>/dev/null \
      || "${CXX}" -O3 -std=c++17 -DPOCKETFFT_CACHE_SIZE="${cs}" -I"${INC}" \
         "${BIN_DIR}/fft-cache-sweep-probe.cxx" -o "${bin}"
    printf '   '; "${bin}" "${REPS}" "${sizes}"
  done
done
