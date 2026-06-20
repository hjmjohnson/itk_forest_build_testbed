#!/usr/bin/env bash
# Find constructor-style temporaries passed to push_back/push_front
# (emplace_back/emplace_front candidates). Excludes ThirdParty/.
set -uo pipefail

REPO="${1:-.}"

if ! git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "error: '$REPO' is not a git work tree" >&2
  exit 2
fi

# .push_back( / .push_front( / ->push_back( / ->push_front(
# immediately followed by an Uppercase constructor-style call.
PATTERN='(\.|->)(push_back|push_front)\([A-Z][A-Za-z0-9_:<>]*\('

hits=$(git -C "$REPO" grep -nE "$PATTERN" -- \
  '*.h' '*.hxx' '*.cxx' '*.cpp' '*.cc' \
  ':(exclude)*ThirdParty/*' ':(exclude)*third_party/*' 2>/dev/null)

if [ -n "$hits" ]; then
  printf '%s\n' "$hits"
fi

count=$(printf '%s' "$hits" | grep -c . )
echo "----"
echo "match_count: $count"
