#!/usr/bin/env bash
# Detect uninitialized non-static data members (m_Foo;) in class headers.
# Flags members with no in-class initializer; skips static/=/{/reference.
# Excludes ThirdParty/. Portable (Linux + macOS), glob-safe (git grep).
set -uo pipefail

REPO="${1:-.}"

# Member-decl pattern: indented   <type> m_Name[opt-array] ;   [opt-comment]
# Excludes lines with '=' or '{' (already initialized) and '&' (reference).
PAT='^[[:space:]]+[A-Za-z_][A-Za-z0-9_:<>,* ]*[ *]m_[A-Za-z0-9_]+(\[[^]]*\])?[[:space:]]*;[[:space:]]*(//.*)?$'
# Statement keywords that masquerade as a "type" (return m_X; etc.) — not decls.
# Matched after the "path:lineno:" prefix git grep / grep -n emit.
STMT=':[[:space:]]*(return|delete|throw|co_return)\b'

cd "$REPO" || { echo "cannot cd to $REPO" >&2; exit 2; }

filter() { grep -vE '\bstatic\b' | grep -vE '&[[:space:]]*m_' | grep -vE "$STMT"; }

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  HITS=$(git grep -nE "$PAT" -- '*.h' '*.hxx' \
            ':(exclude)*ThirdParty/*' ':(exclude)*/ThirdParty/*' 2>/dev/null | filter)
else
  HITS=$(grep -rnE "$PAT" --include='*.h' --include='*.hxx' . 2>/dev/null \
         | grep -v '/ThirdParty/' | filter)
fi

if [ -n "$HITS" ]; then
  printf '%s\n' "$HITS"
fi

COUNT=$(printf '%s' "$HITS" | grep -c . || true)
echo "---"
echo "match_count: $COUNT"
