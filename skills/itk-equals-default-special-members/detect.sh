#!/usr/bin/env bash
# Detect hand-written empty-body special members that should be `= default`.
#   $1 = repo path (default: .)
# Excludes ThirdParty/. Uses git grep with pathspecs (glob-safe).
set -uo pipefail

repo="${1:-.}"
cd "$repo" || { echo "no such dir: $repo" >&2; exit 2; }

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "not a git work tree: $repo" >&2; exit 2
fi

exts=(':(glob)**/*.h' ':(glob)**/*.hxx' ':(glob)**/*.cxx' ':(glob)**/*.hpp' ':(glob)**/*.cpp')
not_tp=(':(exclude,glob)**/ThirdParty/**' ':(exclude,glob)ThirdParty/**')

# In-class empty-body special member: Name(...) [override] {}  with empty {}.
# Heuristic: an identifier (optionally ~), a paren group, optional override,
# then "{}" (possibly spaced) optionally followed by ';'.
inclass_re='(^|[[:space:]])~?[A-Za-z_][A-Za-z0-9_]*[[:space:]]*\([^)]*\)[[:space:]]*(override[[:space:]]*)?\{[[:space:]]*\}[[:space:]]*;?'

# Out-of-line empty destructor body on one line: T::~T(...) {}
outline_re='[A-Za-z_][A-Za-z0-9_]*::~[A-Za-z_][A-Za-z0-9_]*[[:space:]]*\([^)]*\)[[:space:]]*\{[[:space:]]*\}'

tmp_in="$(mktemp)"; tmp_out="$(mktemp)"
trap 'rm -f "$tmp_in" "$tmp_out"' EXIT

git grep -nE "$inclass_re"  -- "${exts[@]}" "${not_tp[@]}" >"$tmp_in"  2>/dev/null
git grep -nE "$outline_re"  -- "${exts[@]}" "${not_tp[@]}" >"$tmp_out" 2>/dev/null

# Drop: already-defaulted lines; non-empty bodies (anything but whitespace
# between the braces); and comment-block tails (line ends with */), which are
# the dominant false positives.
grep -vE '=[[:space:]]*default' "$tmp_in" \
  | grep -vE '\{[[:space:]]*[^}[:space:]]' \
  | grep -vE '\*/[[:space:]]*$' >"$tmp_in.f" || true
mv "$tmp_in.f" "$tmp_in"

n_in=$(wc -l <"$tmp_in" | tr -d ' ')
n_out=$(wc -l <"$tmp_out" | tr -d ' ')

if [ "$n_in" -gt 0 ]; then
  echo "== in-class empty-body special members ( {} -> = default ) =="
  sed 's/^/  /' "$tmp_in"
fi
if [ "$n_out" -gt 0 ]; then
  echo "== out-of-line empty destructor bodies [out-of-line, review-only] =="
  sed 's/^/  /' "$tmp_out"
fi

total=$((n_in + n_out))
echo
echo "in-class candidates : $n_in"
echo "out-of-line bodies  : $n_out"
echo "total candidate sites: $total"

[ "$total" -gt 0 ]
