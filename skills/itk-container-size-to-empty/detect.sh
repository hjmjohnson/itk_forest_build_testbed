#!/usr/bin/env bash
# Find container size-vs-zero emptiness tests that should use empty().
# Candidates only: type-aware filtering is clang-tidy's job (see SKILL.md).
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../lib/detect-common.sh"

# Emptiness-equivalent comparisons only:
#   ... vs 0 :  == 0 , != 0 , <= 0 , > 0 , >= 0  (>= 0 is trivially true; tidy ignores)
#   ... vs 1 :  < 1   , >= 1
# Deliberately excludes == 1, > 1, <= 1, etc. (those are NOT emptiness tests).
PATTERN='\.(size|length)\(\)[[:space:]]*(([=!]=|<=|>=?)[[:space:]]*0|(<|>=)[[:space:]]*1)\b'

itk_detect_init "${1:-.}"

hits="$(itk_detect_grep "$PATTERN" "${ITK_DETECT_SOURCES[@]}")"
[ -n "$hits" ] && printf '%s\n' "$hits"

itk_detect_report "$(itk_detect_count "$hits")"
