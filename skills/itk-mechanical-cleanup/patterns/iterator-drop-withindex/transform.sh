#!/usr/bin/env bash
# Assisted, use-analysis-gated rewrite of index-free WithIndex iterators to the
# plain ImageRegion[Const]Iterator, plus the matching #include swap.
#
#   transform.sh [repo-path]            dry-run (default): list what would change
#   transform.sh [repo-path] --apply    write changes in place (never commits)
#
# Safety: a file is rewritten ONLY when it declares >=1 WithIndex iterator and
# contains NO .GetIndex( / .GetIndexInternal( anywhere -> the safe common case.
# Files mixing index-using and index-free iterators are reported and SKIPPED.
set -uo pipefail

REPO="."
APPLY=0
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    *) REPO="$a" ;;
  esac
done

cd "$REPO" || { echo "not a directory: $REPO" >&2; exit 2; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repo: $REPO" >&2; exit 2; }

DECL_RE='ImageRegion(Const)?IteratorWithIndex<'

mapfile -t FILES < <(
  git grep -lE "$DECL_RE" -- \
    '*.h' '*.hxx' '*.cxx' '*.txx' \
    ':!*ThirdParty*' ':!*/ThirdParty/*'
)

# portable in-place edit (Linux GNU + macOS BSD sed)
sed_inplace() {
  if sed --version >/dev/null 2>&1; then sed -i "$@"; else sed -i '' "$@"; fi
}

changed=0
skipped=0
for f in "${FILES[@]}"; do
  if grep -qE '\.GetIndex(Internal)?\(' "$f"; then
    echo "SKIP  $f  (calls GetIndex; manual per-variable review)"
    skipped=$((skipped + 1))
    continue
  fi
  echo "REWRITE  $f"
  grep -nE "$DECL_RE|itkImageRegion(Const)?IteratorWithIndex\.h" "$f" | sed 's/^/    /'
  if [[ "$APPLY" -eq 1 ]]; then
    # type token: ...ConstIteratorWithIndex -> ...ConstIterator ; ...IteratorWithIndex -> ...Iterator
    sed_inplace -E \
      -e 's/ImageRegionConstIteratorWithIndex/ImageRegionConstIterator/g' \
      -e 's/ImageRegionIteratorWithIndex/ImageRegionIterator/g' \
      -e 's/itkImageRegionConstIteratorWithIndex\.h/itkImageRegionConstIterator.h/g' \
      -e 's/itkImageRegionIteratorWithIndex\.h/itkImageRegionIterator.h/g' \
      "$f"
  fi
  changed=$((changed + 1))
done

echo
if [[ "$APPLY" -eq 1 ]]; then
  echo "Rewrote ${changed} file(s); skipped ${skipped} mixed file(s). Review 'git diff' and rebuild+test."
else
  echo "[dry-run] Would rewrite ${changed} file(s); ${skipped} mixed file(s) need manual review."
  echo "Re-run with --apply to write."
fi
