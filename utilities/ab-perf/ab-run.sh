#!/usr/bin/env bash
# ab-run.sh — end-to-end A/B timing + correctness comparison of ONE consumer
# built against two dependency variants (e.g. ITK main vs an ITK PR), using the
# forest layout of this testbed.
#
# Assumes both forests are ALREADY BUILT (this script only times + compares; it
# does not build). It locates the consumer's inner ctest tree, times the named
# subset on each side with identical methodology, and prints a noise-aware diff.
#
# Usage:
#   ab-run.sh <consumer> <regex> <A-forest> <B-forest> [repeats] [out-dir]
# Example:
#   ab-run.sh ANTs 'ANTS_ROT|ANTS_SYN' build_forest-itkv6_main build_forest-pr6487 5
#
# Clean-isolation requirement (see README.md): the consumer SOURCE must be
# identical in both forests; only the dependency under test may differ.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CONS="${1:?consumer (e.g. ANTs, BRAINSTools)}"; RE="${2:?ctest name regex}"
AF="${3:?A forest dir}"; BF="${4:?B forest dir}"; REP="${5:-5}"
OUT="${6:-$ROOT/.devlocal/ab-perf/$(echo "$CONS" | tr / _)}"
mkdir -p "$OUT"

# Resolve a consumer's inner ctest tree (the dir holding CTestTestfile.cmake
# with the most registered tests under <forest>/<consumer>-build).
find_inner(){
  local f="$1"; local base="$f/${CONS}-build" best="" bestn=-1 d n
  [ -d "$base" ] || { printf '\n'; return 0; }
  while IFS= read -r d; do
    n=$(cd "$d" && ctest -N 2>/dev/null | grep -c 'Test #'); n=${n:-0}
    if [ "$n" -gt "$bestn" ] 2>/dev/null; then bestn=$n; best="$d"; fi
  done < <(find "$base" -name CTestTestfile.cmake -printf '%h\n' 2>/dev/null)
  printf '%s\n' "$best"
}

AB_A="$(find_inner "$ROOT/$AF")"; AB_B="$(find_inner "$ROOT/$BF")"
[ -n "$AB_A" ] && [ -n "$AB_B" ] || { echo "could not locate ${CONS} ctest tree in one forest" >&2; exit 2; }
echo "A tree: $AB_A"; echo "B tree: $AB_B"

bash "$HERE/time-ctest.sh" "$AB_A" "${CONS}_A" "$OUT" "$REP" "$RE"
bash "$HERE/time-ctest.sh" "$AB_B" "${CONS}_B" "$OUT" "$REP" "$RE"

echo; echo "===== A/B COMPARISON: $CONS ====="
python3 "$HERE/ab-compare.py" "$OUT/${CONS}_A_summary.tsv" "$OUT/${CONS}_B_summary.tsv" \
  --a-label "$AF" --b-label "$BF"
echo; echo "env A:"; cat "$OUT/${CONS}_A_env.txt"
