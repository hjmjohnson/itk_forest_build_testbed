#!/usr/bin/env bash
# Find `if (<dimension-constant> <cmp> <int>)` and `if (...SystemIsBigEndian())`
# candidate sites for migration to `if constexpr`. Each hit is a CANDIDATE:
# verify the operand is a constant expression before rewriting (review-only).
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../lib/detect-common.sh"

DIM='(V?Dimension|T?PointDimension|ImageDimension|InputImageDimension|OutputImageDimension)'
DIM_RE="if[[:space:]]*\([[:space:]]*${DIM}[[:space:]]*(==|!=|>=|<=|>|<)[[:space:]]*[0-9]"
BSWAP_RE='if[[:space:]]*\([^)]*SystemIsBigEndian[[:space:]]*\('

itk_detect_init "${1:-.}"

hits="$(
    itk_detect_grep "$DIM_RE" "${ITK_DETECT_SOURCES[@]}"
    itk_detect_grep "$BSWAP_RE" "${ITK_DETECT_SOURCES[@]}"
)"
# Drop already-migrated `if constexpr`, sort/unique by file:line.
hits="$(printf '%s\n' "$hits" | grep -v 'if constexpr' | grep -v '^$' \
        | sort -t: -k1,1 -k2,2n -u)" || true
[ -n "$hits" ] && printf '%s\n' "$hits"

itk_detect_report "$(itk_detect_count "$hits")" \
    '(CANDIDATES — verify the operand is constexpr before rewriting)'
