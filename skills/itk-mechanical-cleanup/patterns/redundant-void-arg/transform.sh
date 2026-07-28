#!/usr/bin/env bash
# sed fallback for redundant (void) removal. REVIEW-ONLY: cannot distinguish
# C-interop / function-pointer sites. Prefer clang-tidy modernize-redundant-void-arg.
# Usage: transform.sh [repo-path] [--apply]   (dry-run by default; never commits)
set -uo pipefail

repo="."
apply=0
for a in "$@"; do
  case "$a" in
    --apply) apply=1 ;;
    *) repo="$a" ;;
  esac
done

cd "$repo" || { echo "no such dir: $repo" >&2; exit 2; }

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  mapfile -t files < <(git grep -lE '\([[:space:]]*void[[:space:]]*\)' -- \
        '*.h' '*.hxx' '*.cxx' '*.cpp' '*.cc' \
        ':!*ThirdParty/*' ':!*/ThirdParty/*' 2>/dev/null)
else
  mapfile -t files < <(grep -rlE --include='*.h' --include='*.hxx' \
        --include='*.cxx' --include='*.cpp' --include='*.cc' \
        '\([[:space:]]*void[[:space:]]*\)' . 2>/dev/null | grep -v '/ThirdParty/')
fi

# (void) -> () only when preceded by an identifier char (a call/decl site),
# never a bare cast like (void)x. Skips lines with extern "C" or typedef.
expr='s/([[:space:]]*void[[:space:]]*)/()/g'

changed=0
for f in "${files[@]}"; do
  [ -n "$f" ] || continue
  before=$(grep -nE '[A-Za-z0-9_>][[:space:]]*\([[:space:]]*void[[:space:]]*\)' "$f" \
        | grep -vE 'extern[[:space:]]+"C"|typedef|\(\*' || true)
  [ -n "$before" ] || continue
  echo "== $f =="
  printf '%s\n' "$before"
  changed=$((changed + 1))
  if [ "$apply" -eq 1 ]; then
    # apply only on qualifying lines (skip typedef/extern "C"/fn-ptr)
    perl -i -pe 'next if /extern\s+"C"|typedef|\(\*/; s/([A-Za-z0-9_>])\s*\(\s*void\s*\)/$1()/g' "$f"
  fi
done

echo "----"
if [ "$apply" -eq 1 ]; then
  echo "applied to $changed file(s) (REVIEW the diff; never committed)"
else
  echo "dry-run: $changed file(s) have candidate sites. Re-run with --apply to write."
  echo "PREFERRED: clang-tidy --checks='-*,modernize-redundant-void-arg' --fix"
fi
