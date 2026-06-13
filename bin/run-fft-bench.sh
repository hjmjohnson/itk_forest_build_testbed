#!/usr/bin/env bash
# Benchmark the FFT-backed N3/N4 bias-field correction in ANTs across two
# forests, to quantify the PocketFFT-vs-vnl_fft performance change.
#
#   bash bin/run-fft-bench.sh <forestA> <forestB> [reps] [phantom_size]
#
# Each ANTs N3/N4 executable is run REPS times on one shared phantom; the
# median + min wall-clock per (forest,tool) is reported. Correctness is also
# checked: the two builds' corrected outputs are compared voxelwise.
set -euo pipefail
BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "${BIN_DIR}")"
# Python needs numpy+nibabel (phantom synth + correctness check); the pixi env
# lacks them, so prefer an explicit BENCH_PY, else the first python3 that has both.
PY="${BENCH_PY:-}"
if [ -z "${PY}" ]; then
  for c in python3 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3; do
    "$c" -c 'import numpy, nibabel' 2>/dev/null && { PY="$c"; break; }
  done
fi
[ -n "${PY}" ] || { echo "no python3 with numpy+nibabel; set BENCH_PY" >&2; exit 1; }
A="${1:-build_forest}"; B="${2:-build_forest-itkv6_main}"
REPS="${3:-5}"; SZ="${4:-128}"
OUT="${ROOT}/.devlocal/fft-bench"; mkdir -p "${OUT}"
PHANTOM="${OUT}/phantom_${SZ}.nii.gz"
[ -f "${PHANTOM}" ] || "${PY}" "${BIN_DIR}/make-bias-phantom.py" "${PHANTOM}" "${SZ}"

exe(){ find "${ROOT}/$1/ANTs-build" -name "$2" -type f 2>/dev/null | head -1; }
median(){ sort -n | awk '{a[NR]=$1} END{print (NR%2)?a[(NR+1)/2]:(a[NR/2]+a[NR/2+1])/2}'; }
ncpu=$( (nproc 2>/dev/null) || sysctl -n hw.ncpu 2>/dev/null || echo 4 )
load1(){ uptime | sed -E 's/.*averages?: *([0-9.]+).*/\1/'; }

# Gate: refuse to measure on a busy machine. Wait up to LOAD_WAIT s for the
# 1-min load to fall below LOAD_MAX (default 30% of CPU count); abort if it
# never does. Set LOAD_MAX=999 to bypass (NOT recommended — numbers are junk).
LOAD_MAX="${LOAD_MAX:-$(awk -v n="${ncpu}" 'BEGIN{printf "%.1f", n*0.3}')}"
LOAD_WAIT="${LOAD_WAIT:-0}"
gate_load(){
  local waited=0 l
  while :; do
    l=$(load1)
    awk -v l="${l}" -v m="${LOAD_MAX}" 'BEGIN{exit !(l<=m)}' && { echo "  load ${l} <= ${LOAD_MAX} OK"; return 0; }
    [ "${waited}" -ge "${LOAD_WAIT}" ] && {
      echo "  ABORT: load ${l} > ${LOAD_MAX} on ${ncpu} CPUs (waited ${waited}s). Stop other builds or raise LOAD_WAIT." >&2
      return 1; }
    echo "  load ${l} > ${LOAD_MAX}; waiting (${waited}/${LOAD_WAIT}s)..."; sleep 30; waited=$((waited+30))
  done
}

time_one(){ # forest tool args... -> echoes seconds, writes outimg
  local forest="$1" tool="$2"; shift 2
  local bin; bin="$(exe "${forest}" "${tool}")"
  [ -x "${bin}" ] || { echo NA; return; }
  local outimg="${OUT}/${tool}_${forest//\//_}.nii.gz" tf="${OUT}/.time.$$"
  /usr/bin/time -p -o "${tf}" "${bin}" "$@" "${outimg}" >/dev/null 2>&1 || true
  awk '/^real/{print $2}' "${tf}"; rm -f "${tf}"
}

echo "=== FFT bias-correction benchmark (phantom ${SZ}^3, reps=${REPS}) ==="
echo "host=$(hostname -s)  cpus=${ncpu}  A=${A}  B=${B}  LOAD_MAX=${LOAD_MAX}"
gate_load || exit 2
for tool in N3BiasFieldCorrection N4BiasFieldCorrection; do
  echo "-- ${tool}"
  # Fixed iterations so the FFT count is identical across builds. N3 and N4
  # take different convergence-flag forms.
  if [ "${tool}" = N4BiasFieldCorrection ]; then
    args=(-d 3 -i "${PHANTOM}" -s 2 -c "[100x100x100x100,0.0]" -b "[80,3]" -o)
  else
    args=(-d 3 -i "${PHANTOM}" -s 2 -c "[200,0.0]" -b "[80,3]" -t "[0.15,0.01,200]" -o)
  fi
  # Interleave reps A,B,A,B... so any thermal/scheduler drift is shared, never
  # charged to one backend. Serial by construction: one process at a time.
  declare -a ta=() tb=()
  for r in $(seq "${REPS}"); do
    ta+=("$(time_one "${A}" "${tool}" "${args[@]}")")
    tb+=("$(time_one "${B}" "${tool}" "${args[@]}")")
  done
  ma=$(printf '%s\n' "${ta[@]}" | median); na=$(printf '%s\n' "${ta[@]}" | sort -n | head -1)
  mb=$(printf '%s\n' "${tb[@]}" | median); nb=$(printf '%s\n' "${tb[@]}" | sort -n | head -1)
  printf '  %-12s A median=%6ss min=%6ss   B median=%6ss min=%6ss   reps=[A:%s][B:%s]\n' \
    "${tool}" "${ma}" "${na}" "${mb}" "${nb}" "${ta[*]}" "${tb[*]}"
  oa="${OUT}/${tool}_${A//\//_}.nii.gz"; ob="${OUT}/${tool}_${B//\//_}.nii.gz"
  if [ -f "${oa}" ] && [ -f "${ob}" ]; then
    "${PY}" - "${oa}" "${ob}" <<'PY'
import sys, numpy as np, nibabel as nib
a=nib.load(sys.argv[1]).get_fdata(); b=nib.load(sys.argv[2]).get_fdata()
d=np.abs(a-b); rng=np.ptp(a) or 1
print(f"  correctness: max|A-B|={d.max():.4g}  mean={d.mean():.4g}  rel={d.max()/rng:.2e}")
PY
  fi
done
