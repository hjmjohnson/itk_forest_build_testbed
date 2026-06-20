#!/usr/bin/env bash
# Flag ImageRegion[Const]IteratorWithIndex declarations whose enclosing file
# never reads the index (.GetIndex / .GetIndexInternal) -> drop-WithIndex
# candidates. Review-gated: files with both a decl AND a GetIndex call are
# reported as REVIEW (may mix index-using and index-free iterators).
set -uo pipefail

REPO="${1:-.}"
cd "$REPO" || { echo "not a directory: $REPO" >&2; exit 2; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repo: $REPO" >&2; exit 2; }

# Declaration sites: "...IteratorWithIndex<...> name(" or "= ...IteratorWithIndex<...>;"
# Exclude ThirdParty and doc-comment cross-reference lines.
DECL_RE='ImageRegion(Const)?IteratorWithIndex<'

mapfile -t HITS < <(
  git grep -nE "$DECL_RE" -- \
    '*.h' '*.hxx' '*.cxx' '*.txx' \
    ':!*ThirdParty*' ':!*/ThirdParty/*' \
  | grep -vE '\\sa|^\S+:[0-9]+:[[:space:]]*\*|^\S+:[0-9]+:[[:space:]]*//'
)

candidate=0
review=0
declare -A SEEN_FILE

print_file_class() {
  local file="$1"
  if git grep -qE '\.GetIndex(Internal)?\(' -- "$file"; then
    echo "REVIEW (file also calls GetIndex; check per-variable)"
    return 1
  fi
  echo "CANDIDATE (no GetIndex in file)"
  return 0
}

for line in "${HITS[@]}"; do
  file="${line%%:*}"
  echo "$line"
  if [[ -z "${SEEN_FILE[$file]:-}" ]]; then
    SEEN_FILE[$file]=1
    printf '    -> '
    if print_file_class "$file"; then
      candidate=$((candidate + 1))
    else
      review=$((review + 1))
    fi
  fi
done

echo
echo "WithIndex declaration lines: ${#HITS[@]}"
echo "CANDIDATE files (no GetIndex, safe to rewrite): ${candidate}"
echo "REVIEW files (mixed; manual per-variable check): ${review}"

[[ "${#HITS[@]}" -gt 0 ]]
