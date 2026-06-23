#!/usr/bin/env bash
# run-pr6487-ab.sh — rigorous, SINGLE-THREADED A/B run for ITK PR #6487
# (vnl_svd -> Eigen itk::Math::SVD) downstream perf + correctness.
#
# Run this OUTSIDE the Claude/agent interface, on a quiesced host, so the
# processes run at nice 0 (no agent nice=5 penalty) with nothing else loading
# the machine. It forces single-threaded execution (NSLOTS=1 +
# ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=1 + OMP/OpenBLAS=1) so each test's wall
# time is deterministic and comparable. Hand the printed log file back to Claude.
#
#   pixi run bash utilities/ab-perf/run-pr6487-ab.sh
#
# Knobs (env):
#   REPEATS=10        timing repeats per test (more = tighter CIs)
#   A_FOREST=build_forest-itkv6_main   baseline forest (ITK main)
#   B_FOREST=build_forest-pr6487       PR forest (ITK #6487)
#   FULL_TIMING=1     time the ENTIRE suite (not just the SVD-hot subset)
#   SMOKE=1           plumbing check: skip correctness, 1 repeat, one trivial test
#
# It must be run with the pixi toolchain active (for ctest); the guard below
# reminds you if not.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
REPEATS="${REPEATS:-10}"
A_FOREST="${A_FOREST:-build_forest-itkv6_main}"
B_FOREST="${B_FOREST:-build_forest-pr6487}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$ROOT/.devlocal/ab-perf/pr6487-rigorous-$STAMP"
LOG="$OUT/run.log"
mkdir -p "$OUT"

command -v ctest >/dev/null 2>&1 || {
  echo "ctest not on PATH — run under the pixi toolchain:"
  echo "    cd $ROOT && pixi run bash utilities/ab-perf/run-pr6487-ab.sh"; exit 1; }

# ---- force single-threaded, deterministic execution -----------------------
export NSLOTS=1
export ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export ITK_USE_THREADPOOL=${ITK_USE_THREADPOOL:-1}

# consumer -> SVD-hot (deformable, DisplacementFieldTransform) test regex
ANTS_SVD='ANTS_ROT_GSYN|ANTS_ROT_EXP|ANTS_SYN_WITH_TIME|antsRegistrationTest_SyN'
BFIT_SVD='BRAINSFitTest_BSpline'

# locate a consumer's inner ctest tree: the dir from which `ctest -N` reports the
# MOST tests (i.e. the project root that aggregates all subdirs, not a leaf).
find_inner(){
  local base="$ROOT/$1/${2}-build" best="" bestn=-1 d n
  [ -d "$base" ] || { printf '\n'; return 0; }
  while IFS= read -r d; do
    n=$(cd "$d" && ctest -N 2>/dev/null | grep -c 'Test #'); n=${n:-0}
    if [ "$n" -gt "$bestn" ] 2>/dev/null; then bestn=$n; best="$d"; fi
  done < <(find "$base" -name CTestTestfile.cmake -printf '%h\n' 2>/dev/null)
  printf '%s\n' "$best"
}

log(){ echo "$@" | tee -a "$LOG"; }

# environment provenance — lets the analyst confirm it was a clean run
{
  echo "==================== run-pr6487-ab.sh ===================="
  echo "stamp           : $STAMP"
  echo "host            : $(uname -n)"
  echo "kernel          : $(uname -sr)"
  echo "nproc           : $(nproc 2>/dev/null)"
  echo "niceness        : $(ps -o ni= -p $$ | tr -d ' ')   (want 0 — outside the agent)"
  echo "loadavg         : $(cut -d' ' -f1-3 /proc/loadavg 2>/dev/null)"
  echo "cpu governor    : $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo n/a)"
  echo "REPEATS         : $REPEATS"
  echo "single-thread   : NSLOTS=$NSLOTS ITK_THREADS=$ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS OMP=$OMP_NUM_THREADS"
  itkver(){ local f="$ROOT/$1/ITK/CMake/itkVersion.cmake"; awk -F'"' '/ITK_VERSION_(MAJOR|MINOR|PATCH)/{print $2}' "$f" 2>/dev/null | paste -sd. ; }
  echo "A_FOREST (base) : $A_FOREST  (ITK $(itkver "$A_FOREST"))"
  echo "B_FOREST (PR)   : $B_FOREST  (ITK $(itkver "$B_FOREST"))"
  echo "ITK A SHA       : $(git -C "$ROOT/$A_FOREST/ITK" rev-parse HEAD 2>/dev/null)"
  echo "ITK B SHA       : $(git -C "$ROOT/$B_FOREST/ITK" rev-parse HEAD 2>/dev/null)"
  echo "=========================================================="
} | tee "$LOG"

run_consumer(){
  local consumer="$1" svd_re="$2" smoke_re="$3"
  local ab_a ab_b; ab_a="$(find_inner "$A_FOREST" "$consumer")"; ab_b="$(find_inner "$B_FOREST" "$consumer")"
  log ""; log "########################## $consumer ##########################"
  if [ -z "$ab_a" ] || [ -z "$ab_b" ]; then
    log "  SKIP $consumer — not built in one or both forests (A='$ab_a' B='$ab_b')"; return; fi
  log "  A tree: $ab_a"; log "  B tree: $ab_b"

  # ---- correctness: full suite once per forest (single-threaded) ----
  if [ "${SMOKE:-0}" != 1 ]; then
    for side in A B; do
      local ab; [ "$side" = A ] && ab="$ab_a" || ab="$ab_b"
      log ""; log "  --- $consumer correctness (FULL suite, -j1) [$side] ---"
      ( cd "$ab" && ctest -j1 --timeout 3600 ) > "$OUT/${consumer}_${side}_correctness.log" 2>&1 || true
      grep -E 'tests passed|failed out of|Total Test time' "$OUT/${consumer}_${side}_correctness.log" | tail -2 | sed 's/^/    /' | tee -a "$LOG"
      awk '/tests FAILED:/{f=1} f' "$OUT/${consumer}_${side}_correctness.log" | grep -E '^[[:space:]]*[0-9]+ - ' | sed 's/^/    FAILED:/' | tee -a "$LOG" || true
    done
  fi

  # ---- timing: SVD-hot subset (or full suite if FULL_TIMING=1; one trivial test if SMOKE) ----
  local re="$svd_re"
  [ "${FULL_TIMING:-0}" = 1 ] && re='.'
  [ "${SMOKE:-0}" = 1 ] && re="$smoke_re"
  log ""; log "  --- $consumer timing (regex='$re', $REPEATS repeats, -j1) ---"
  bash "$HERE/time-ctest.sh" "$ab_a" "${consumer}_A" "$OUT" "$REPEATS" "$re" 2>&1 | sed 's/^/    /' | tee -a "$LOG"
  bash "$HERE/time-ctest.sh" "$ab_b" "${consumer}_B" "$OUT" "$REPEATS" "$re" 2>&1 | sed 's/^/    /' | tee -a "$LOG"
  log ""; log "  --- $consumer A/B comparison (noise-aware) ---"
  python3 "$HERE/ab-compare.py" "$OUT/${consumer}_A_summary.tsv" "$OUT/${consumer}_B_summary.tsv" \
    --a-label "$A_FOREST" --b-label "$B_FOREST" 2>&1 | sed 's/^/    /' | tee -a "$LOG"
}

run_consumer ANTs "$ANTS_SVD" 'PrintHeader_HELP_SHORT'
run_consumer BRAINSTools "$BFIT_SVD" 'insertMidACPCpointTest'

log ""
log "=========================================================="
log "DONE. Hand this log back to Claude:"
log "    $LOG"
log "(raw per-repeat samples + per-side summaries are alongside it in $OUT)"
