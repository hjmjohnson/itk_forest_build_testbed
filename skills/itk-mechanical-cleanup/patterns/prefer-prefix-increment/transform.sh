#!/usr/bin/env bash
# Rewrite discarded-value postfix increment/decrement to prefix form.
#   IDENT++;  -> ++IDENT;     IDENT--;  -> --IDENT;
#   for(...;...; IDENT++) -> for(...;...; ++IDENT)   (likewise --)
# Dry-run by default; --apply writes in place. Never commits.
# Only the two unambiguous statement/for-clause shapes are touched.
set -uo pipefail

APPLY=0
REPO="."
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    *) REPO="$a" ;;
  esac
done

cd "$REPO" || { echo "no such dir: $REPO" >&2; exit 2; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "not a git work tree: $REPO" >&2; exit 2; }

PATHSPECS=(
  '*.cxx' '*.hxx' '*.h' '*.cpp' '*.txx'
  ':!:*ThirdParty/*' ':!:*third_party/*' ':!:*/Modules/ThirdParty/*'
)

RE_STMT='^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*(\+\+|--)[[:space:]]*;[[:space:]]*$'
RE_FOR='for[[:space:]]*\([^;]*;[^;]*;[^;()]*[A-Za-z_][A-Za-z0-9_]*(\+\+|--)[[:space:]]*\)'

files="$(git grep -lE "$RE_STMT" -- "${PATHSPECS[@]}" 2>/dev/null
         git grep -lE "$RE_FOR"  -- "${PATHSPECS[@]}" 2>/dev/null | sort -u)"
files="$(printf '%s\n' "$files" | grep -vE '^$' | sort -u)"

[ -z "$files" ] && { echo "no candidate sites"; exit 0; }

# Portable in-place edit via perl (Linux+macOS identical behavior).
# Shape 1: leading-ws IDENT++ ;  ->  leading-ws ++IDENT ;
P_STMT='s/^(\s*)([A-Za-z_]\w*)(\+\+|--)(\s*;\s*)$/$1.($3 eq "++" ? "++" : "--").$2.$4/e'
# Shape 2: IDENT++ )  inside a for header  ->  ++IDENT )
P_FOR='s/([A-Za-z_]\w*)(\+\+|--)(\s*\))/($2 eq "++" ? "++" : "--").$1.$3/ge if /for\s*\([^;]*;[^;]*;/'

changed=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  tmp="$(mktemp)"
  perl -pe "$P_STMT" "$f" | perl -pe "$P_FOR" > "$tmp"
  if ! cmp -s "$f" "$tmp"; then
    changed=$((changed+1))
    if [ "$APPLY" -eq 1 ]; then
      cp "$tmp" "$f"
      echo "edited: $f"
    else
      echo "=== $f ==="
      diff -u "$f" "$tmp" | grep -E '^[+-]' | grep -vE '^[+-]{3}'
    fi
  fi
  rm -f "$tmp"
done <<< "$files"

echo "----"
if [ "$APPLY" -eq 1 ]; then
  echo "files edited: $changed (not committed — review and build before commit)"
else
  echo "files with candidate edits: $changed (dry-run; pass --apply to write)"
fi
