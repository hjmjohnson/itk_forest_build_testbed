#!/usr/bin/env bash
# Find `if (<dimension-constant> <cmp> <int>)` and `if (...SystemIsBigEndian())`
# candidate sites for migration to `if constexpr`. Each hit is a CANDIDATE:
# verify the operand is a constant expression before rewriting (review-only).
set -uo pipefail

REPO="${1:-.}"
cd "$REPO" || { echo "not a directory: $REPO" >&2; exit 2; }

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "not a git work tree: $REPO" >&2; exit 2
fi

DIM='(V?Dimension|T?PointDimension|ImageDimension|InputImageDimension|OutputImageDimension)'
DIM_RE="if[[:space:]]*\([[:space:]]*${DIM}[[:space:]]*(==|!=|>=|<=|>|<)[[:space:]]*[0-9]"
BSWAP_RE='if[[:space:]]*\([^)]*SystemIsBigEndian[[:space:]]*\('

PATHSPECS=( '*.h' '*.hxx'
  ':!*ThirdParty/*' ':!*/ThirdParty/*' ':!Modules/ThirdParty/*' )

hits="$(
  git grep -nE "$DIM_RE" -- "${PATHSPECS[@]}" 2>/dev/null
  git grep -nE "$BSWAP_RE" -- "${PATHSPECS[@]}" 2>/dev/null
)"
# Drop already-migrated `if constexpr`, sort/unique by file:line.
hits="$(printf '%s\n' "$hits" | grep -v 'if constexpr' | grep -v '^$' \
        | sort -t: -k1,1 -k2,2n -u)"

count=0
if [ -n "$hits" ]; then
  printf '%s\n' "$hits"
  count="$(printf '%s\n' "$hits" | wc -l | tr -d ' ')"
fi

echo "----"
echo "candidate sites: $count  (CANDIDATES — verify operand is constexpr before rewrite)"
[ "$count" -gt 0 ]
