#!/usr/bin/env bash
# Find redundant (void) parameter lists in C++ sources.
# Usage: detect.sh [repo-path]   (default: .)
set -uo pipefail

repo="${1:-.}"
cd "$repo" || { echo "no such dir: $repo" >&2; exit 2; }

# identifier (possibly qualified/templated/dtor) immediately followed by (void)
pat='[A-Za-z_~][A-Za-z0-9_:<>~]*[[:space:]]*\([[:space:]]*void[[:space:]]*\)'

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  hits=$(git grep -nE "$pat" -- \
        '*.h' '*.hxx' '*.cxx' '*.cpp' '*.cc' \
        ':!*ThirdParty/*' ':!*/ThirdParty/*' 2>/dev/null)
else
  hits=$(grep -rnE --include='*.h' --include='*.hxx' --include='*.cxx' \
        --include='*.cpp' --include='*.cc' "$pat" . 2>/dev/null \
        | grep -v '/ThirdParty/')
fi

if [ -n "$hits" ]; then
  printf '%s\n' "$hits"
fi

count=$(printf '%s' "$hits" | grep -c . 2>/dev/null || true)
echo "----"
echo "candidate (void) sites: ${count:-0}"
echo "(function-pointer typedefs / extern \"C\" are false positives; clang-tidy is the arbiter)"
