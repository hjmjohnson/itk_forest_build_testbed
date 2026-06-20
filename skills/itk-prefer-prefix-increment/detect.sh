#!/usr/bin/env bash
# Find discarded-value postfix increment/decrement sites that should be prefix.
# Two shapes only:
#   1. standalone statement:   IDENT++;   IDENT--;
#   2. for-increment clause:    for(...; ...; IDENT++)   IDENT--)
# ThirdParty/ excluded. Value-consuming postfix (a[i++], *p++, x=it++) NOT matched.
set -uo pipefail

REPO="${1:-.}"
cd "$REPO" || { echo "no such dir: $REPO" >&2; exit 2; }

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "not a git work tree: $REPO" >&2
  exit 2
fi

PATHSPECS=(
  '*.cxx' '*.hxx' '*.h' '*.cpp' '*.txx'
  ':!:*ThirdParty/*' ':!:*third_party/*' ':!:*/Modules/ThirdParty/*'
)

# Shape 1: an identifier immediately followed by ++ or -- that is the whole
# statement (optional leading whitespace, terminating ';'). Excludes a[i]++;
# style by requiring the token before ++/-- to be a bare identifier at stmt start.
RE_STMT='^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*(\+\+|--)[[:space:]]*;[[:space:]]*$'

# Shape 2: for-increment clause — a for header whose 3rd clause ends IDENT++)
# (or --). Requires two ';' inside the for(...) before the IDENT++/-- token.
RE_FOR='for[[:space:]]*\([^;]*;[^;]*;[^;()]*[A-Za-z_][A-Za-z0-9_]*(\+\+|--)[[:space:]]*\)'

stmt_hits="$(git grep -nE "$RE_STMT" -- "${PATHSPECS[@]}" 2>/dev/null)"
for_hits="$(git grep -nE "$RE_FOR" -- "${PATHSPECS[@]}" 2>/dev/null)"

all="$(printf '%s\n%s\n' "$stmt_hits" "$for_hits" | grep -vE '^$' | sort -u)"

if [ -n "$all" ]; then
  printf '%s\n' "$all"
fi

count="$(printf '%s' "$all" | grep -cE '.' )"
echo "----"
echo "candidate discarded-value postfix sites: $count"
