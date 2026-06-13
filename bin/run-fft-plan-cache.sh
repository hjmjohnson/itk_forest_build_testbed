#!/usr/bin/env bash
# Side test: quantify the benefit of SAVING the FFT plan when many same-size
# transforms run (the N3/N4 histogram-FFT pattern). Builds the probe with the
# PocketFFT plan cache OFF vs ON and reports ns/transform for each.
#
#   bash bin/run-fft-plan-cache.sh [length] [reps]
set -euo pipefail
BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "${BIN_DIR}")"
N="${1:-256}"; REPS="${2:-200000}"
OUT="${ROOT}/.devlocal/fft-bench"; mkdir -p "${OUT}"
# pocketfft header ships inside any built ITK FFT include dir; find one.
INC=$(find "${ROOT}"/build_forest*/ITK/Modules/Filtering/FFT/include -name pocketfft_hdronly.h 2>/dev/null | head -1)
INC="${INC%/*}"
[ -n "${INC}" ] && [ -f "${INC}/pocketfft_hdronly.h" ] || { echo "pocketfft_hdronly.h not found; build ITK first" >&2; exit 1; }
CXX="${CXX:-$(command -v c++ || command -v clang++ || command -v g++)}"

echo "=== FFT plan-cache side test (host=$(hostname -s), pocketfft from ${INC}) ==="
for cs in 0 16; do
  "${CXX}" -O3 -std=c++17 -DPOCKETFFT_CACHE_SIZE="${cs}" -I"${INC}" \
    "${BIN_DIR}/fft-plan-cache-probe.cxx" -o "${OUT}/probe_cs${cs}" -lpthread 2>/dev/null \
    || "${CXX}" -O3 -std=c++17 -DPOCKETFFT_CACHE_SIZE="${cs}" -I"${INC}" \
       "${BIN_DIR}/fft-plan-cache-probe.cxx" -o "${OUT}/probe_cs${cs}"
  printf '  cache=%-2s -> ' "${cs}"; "${OUT}/probe_cs${cs}" "${N}" "${REPS}"
done
echo "Interpretation: cache=0 reconstructs the plan every call (no plan saving);"
echo "cache=16 reuses the saved same-length plan. The gap is the per-call plan-setup"
echo "cost that dominates when the transform itself is tiny (histogram FFT)."
echo "NOTE: pocketfft_hdronly.h defaults POCKETFFT_CACHE_SIZE=0 and ITK does not"
echo "override it -> ITK's PocketFFT backend runs the cache=0 (slow) path as shipped."
