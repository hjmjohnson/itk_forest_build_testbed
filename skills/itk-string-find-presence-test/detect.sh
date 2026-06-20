#!/usr/bin/env bash
# Detect the legacy substring-presence idiom  str.find(sub) < str.(length|size)()
# in ITK-ecosystem C++ sources. ThirdParty/ excluded. Glob-safe (git grep pathspecs).
set -uo pipefail

REPO="${1:-.}"
PAT='\.find\([^)]*\)[[:space:]]*<[[:space:]]*[A-Za-z_][A-Za-z0-9_.]*\.(length|size)\(\)'

if ! git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "error: '$REPO' is not a git work tree" >&2
    exit 2
fi

hits=$(git -C "$REPO" grep -nE "$PAT" -- \
        '*.cxx' '*.hxx' '*.h' '*.cpp' '*.cc' \
        ':(exclude)*ThirdParty*' 2>/dev/null)

if [ -n "$hits" ]; then
    printf '%s\n' "$hits"
fi

count=$(printf '%s' "$hits" | grep -c . || true)
echo "----"
echo "match_count: $count"
