#!/usr/bin/env bash
# compare-itk-refs.sh — build + warning/error + test-status comparison of two
# ITK build trees (default: release-5.4 vs latest main from the forest testbed).
#
# For each tree it: records the ITK ref, (re)builds capturing the full compiler
# log, runs CTest producing a structured Test.xml, then diffs warnings/errors and
# per-test status via analyze_results.py. Verifies builds by artifact, not just
# pipe exit code.
#
# Usage:
#   compare-itk-refs.sh                                  # defaults below
#   compare-itk-refs.sh <labelA>:<buildA> <labelB>:<buildB> [outdir]
#
# Env:
#   BUILD=1            rebuild to capture warnings (0 = reuse existing logs)
#   RUN_CTEST=1        run the test suites (0 = skip, compare build only)
#   CTEST_INCLUDE=re   only run tests matching this regex (ctest -R) to scope
#   CTEST_JOBS=N       parallel test jobs (default ncpu/2)
#   CTEST_TIMEOUT=S    per-test timeout seconds (default 300)
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"                       # testbed repo root

# Toolchain: prefer the pixi env (cmake/ctest/ninja) over system.
BIN="$ROOT/.pixi/envs/default/bin"
CMAKE="$([ -x "$BIN/cmake" ] && echo "$BIN/cmake" || echo cmake)"
CTEST="$([ -x "$BIN/ctest" ] && echo "$BIN/ctest" || echo ctest)"

A_DEFAULT="release-5.4:$ROOT/build_forest-ITK-release-5-4/ITK-build"
B_DEFAULT="main:$ROOT/build_forest-itkv6_main/ITK-build"
A_SPEC="${1:-$A_DEFAULT}"; B_SPEC="${2:-$B_DEFAULT}"
OUT="${3:-$ROOT/.devlocal/itk-compare-$(date +%Y%m%d 2>/dev/null || echo out)}"

BUILD="${BUILD:-1}"; RUN_CTEST="${RUN_CTEST:-1}"
CTEST_JOBS="${CTEST_JOBS:-$(( $(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4) / 2 ))}"
[ "$CTEST_JOBS" -lt 2 ] && CTEST_JOBS=2
CTEST_TIMEOUT="${CTEST_TIMEOUT:-300}"

mkdir -p "$OUT"

# prep <label> <builddir> <tag-out-prefix>  -> echoes "<ref>" ; writes <prefix>.buildlog and <prefix>/Test.xml
prep() {
  local label="$1" bd="$2" pfx="$3"
  [ -f "$bd/CMakeCache.txt" ] || { echo "ERROR: not a CMake build dir: $bd" >&2; return 1; }
  local src ref
  src="$(grep -E '^CMAKE_HOME_DIRECTORY' "$bd/CMakeCache.txt" | head -1 | cut -d= -f2)"
  ref="$(git -C "$src" describe --tags --always --dirty 2>/dev/null || echo unknown)"

  if [ "$BUILD" = "1" ]; then
    echo "[$label] building $bd (ref $ref) ..." >&2
    "$CMAKE" --build "$bd" > "$pfx.buildlog" 2>&1
    local rc=$?
    grep -cE ' error: ' "$pfx.buildlog" >/dev/null 2>&1
    [ "$rc" -ne 0 ] && echo "[$label] build returned non-zero ($rc) — see $pfx.buildlog" >&2
  else
    : > "$pfx.buildlog"   # build skipped; no warnings captured
    echo "[$label] BUILD=0; skipping rebuild (no warning capture)" >&2
  fi

  if [ "$RUN_CTEST" = "1" ]; then
    echo "[$label] running ctest (jobs=$CTEST_JOBS timeout=$CTEST_TIMEOUT${CTEST_INCLUDE:+ -R $CTEST_INCLUDE}) ..." >&2
    ( cd "$bd" && "$CTEST" -T Test -j "$CTEST_JOBS" --timeout "$CTEST_TIMEOUT" \
        ${CTEST_INCLUDE:+-R "$CTEST_INCLUDE"} >/dev/null 2>&1 )
    local tag; tag="$(head -1 "$bd/Testing/TAG" 2>/dev/null)"
    if [ -n "$tag" ] && [ -f "$bd/Testing/$tag/Test.xml" ]; then
      cp "$bd/Testing/$tag/Test.xml" "$pfx.Test.xml"
    else
      echo "[$label] WARNING: no Test.xml produced" >&2; : > "$pfx.Test.xml"
    fi
  else
    : > "$pfx.Test.xml"
  fi
  echo "$ref"
}

A_LABEL="${A_SPEC%%:*}"; A_BUILD="${A_SPEC#*:}"
B_LABEL="${B_SPEC%%:*}"; B_BUILD="${B_SPEC#*:}"

A_REF="$(prep "$A_LABEL" "$A_BUILD" "$OUT/a")" || exit 1
B_REF="$(prep "$B_LABEL" "$B_BUILD" "$OUT/b")" || exit 1

python3 "$HERE/analyze_results.py" \
  --label-a "$A_LABEL" --ref-a "$A_REF" --log-a "$OUT/a.buildlog" --xml-a "$OUT/a.Test.xml" \
  --label-b "$B_LABEL" --ref-b "$B_REF" --log-b "$OUT/b.buildlog" --xml-b "$OUT/b.Test.xml" \
  --out "$OUT/report.md"
rc=$?
echo "" >&2
echo "Report: $OUT/report.md" >&2
exit $rc
