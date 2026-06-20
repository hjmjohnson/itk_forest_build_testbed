#!/usr/bin/env bash
# Find image-iterator construction sites with redundant explicit template args
# that C++17 CTAD can deduce: <IterName><...>( where first arg is an image.
set -uo pipefail

REPO="${1:-.}"
ITERS='ImageRegionConstIteratorWithIndex|ImageRegionIteratorWithIndex|ImageRegionConstIterator|ImageRegionIterator|ImageScanlineConstIterator|ImageScanlineIterator|ImageRegionRange|ImageBufferRange'
PATTERN="(${ITERS})<[^>;]+>[[:space:]]*\("

cd "$REPO" 2>/dev/null || { echo "no such repo: $REPO" >&2; exit 2; }

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  hits=$(git grep -nE "$PATTERN" -- '*.hxx' '*.cxx' ':(exclude)*ThirdParty/*' 2>/dev/null)
else
  hits=$(grep -rnE --include='*.hxx' --include='*.cxx' "$PATTERN" . 2>/dev/null \
         | grep -v '/ThirdParty/')
fi

printf '%s\n' "$hits" | sed '/^$/d'
count=$(printf '%s\n' "$hits" | sed '/^$/d' | grep -c . || true)
echo "----"
echo "match_count: ${count:-0}"
