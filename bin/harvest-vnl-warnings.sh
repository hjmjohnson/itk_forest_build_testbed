#!/usr/bin/env bash
# Harvest vnl_math:: deprecation warnings from the matrix build logs to help
# coordinate follow-up work (which consumers still use deprecated vnl_math::).
# Usage: bash harvest-vnl-warnings.sh [logdir]   (default /tmp)
LOGDIR="${1:-/tmp}"
OUT="${PWD}/.devlocal/vnl-deprecation-report.md"
mkdir -p "$(dirname "$OUT")"

# Map a deprecation message fragment -> category.
categorize(){
  case "$1" in
    *"numeric constants are deprecated"*)        echo "constants" ;;
    *"classification functions are deprecated"*) echo "isnan-family" ;;
    *"vnl_math::abs is deprecated"*)             echo "abs" ;;
    *"vnl_huge_val is deprecated"*)              echo "vnl_huge_val" ;;
    *"is deprecated; use std::max"*|*"std::min"*|*"std::cbrt"*|*"std::hypot"*) echo "std-reexports" ;;
    *"this vnl_math:: function is deprecated"*)  echo "functions" ;;
    *) echo "other-vnl" ;;
  esac
}

{
  echo "# vnl_math:: deprecation warnings — downstream catalog"
  echo "_ITK @ update-vnl-e96c6ab (deprecated vnl vendored); generated from ${LOGDIR}/matrix-*.log_"
  echo
} > "$OUT"

declare -A CAT_COUNT TARGET_COUNT
TMP="$(mktemp)"
for log in "${LOGDIR}"/matrix-*.log; do
  [ -f "$log" ] || continue
  target="$(basename "$log" .log)"; target="${target#matrix-}"
  # clang/gcc deprecation lines that mention vnl
  grep -hE "warning:.*is deprecated:.*(vnl_math|vnl_huge_val)|warning:.*(vnl_math|vnl_huge_val).*is deprecated" "$log" 2>/dev/null \
    | while IFS= read -r line; do
        cat="$(categorize "$line")"
        # extract "<file>:<line>" and the deprecated symbol if present
        loc="$(echo "$line" | grep -oE "[^ ]+:[0-9]+:[0-9]+:" | head -1)"
        sym="$(echo "$line" | grep -oE "'[^']+' is deprecated" | head -1)"
        echo "${target}|${cat}|${sym}|${loc}"
      done
done | sort -u > "$TMP"

echo "## Summary by category" >> "$OUT"
echo >> "$OUT"
echo "| category | distinct warning sites | targets affected |" >> "$OUT"
echo "|---|---|---|" >> "$OUT"
for cat in constants isnan-family functions std-reexports vnl_huge_val abs other-vnl; do
  n=$(awk -F'|' -v c="$cat" '$2==c' "$TMP" | wc -l | tr -d ' ')
  tg=$(awk -F'|' -v c="$cat" '$2==c{print $1}' "$TMP" | sort -u | paste -sd, -)
  [ "$n" -gt 0 ] && echo "| $cat | $n | ${tg} |" >> "$OUT"
done
echo >> "$OUT"
echo "## Per-target counts" >> "$OUT"
echo >> "$OUT"
echo "| target | warning sites |" >> "$OUT"
echo "|---|---|" >> "$OUT"
awk -F'|' '{print $1}' "$TMP" | sort | uniq -c | sort -rn | while read -r c t; do
  echo "| $t | $c |" >> "$OUT"
done
echo >> "$OUT"
echo "## Distinct sites (target | category | symbol | location)" >> "$OUT"
echo '```' >> "$OUT"
column -t -s'|' "$TMP" >> "$OUT" 2>/dev/null || cat "$TMP" >> "$OUT"
echo '```' >> "$OUT"
rm -f "$TMP"

echo "total distinct vnl-deprecation warning sites: $(grep -c '|' "$OUT" 2>/dev/null || echo 0)"
echo "report: $OUT"
