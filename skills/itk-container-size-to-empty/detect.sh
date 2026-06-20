#!/usr/bin/env bash
# Find container size-vs-zero emptiness tests that should use empty().
# Candidates only: type-aware filtering is clang-tidy's job (see SKILL.md).
set -uo pipefail

repo="${1:-.}"
if ! git -C "$repo" rev-parse --git-dir >/dev/null 2>&1; then
  echo "error: '$repo' is not a git repository" >&2
  exit 2
fi

# Emptiness-equivalent comparisons only:
#   ... vs 0 :  == 0 , != 0 , <= 0 , > 0 , >= 0  (>= 0 is trivially true; tidy ignores)
#   ... vs 1 :  < 1   , >= 1
# Deliberately excludes == 1, > 1, <= 1, etc. (those are NOT emptiness tests).
pattern='\.(size|length)\(\)[[:space:]]*(([=!]=|<=|>=?)[[:space:]]*0|(<|>=)[[:space:]]*1)\b'

hits=$(git -C "$repo" grep -nE "$pattern" -- \
        ':!*ThirdParty*' ':!*thirdparty*' \
        ':!*.git*' 2>/dev/null)

if [ -n "$hits" ]; then
  printf '%s\n' "$hits"
fi

count=$(printf '%s' "$hits" | grep -c . || true)
echo "----"
echo "match_count: $count"
[ "$count" -gt 0 ]
