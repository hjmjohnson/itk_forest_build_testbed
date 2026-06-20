#!/usr/bin/env bash
# Detect one-shot itk::ImageFileReader/ImageFileWriter chains that could collapse
# to itk::ReadImage<I>(fn) / itk::WriteImage(src, fn). Review-only: prints
# file:line context for each declaration so a human confirms the New/SetFileName/
# Update chain. Arg $1 = repo path (default .). Excludes ThirdParty/.
set -uo pipefail

repo="${1:-.}"
cd "$repo" || { echo "detect: cannot cd to $repo" >&2; exit 2; }

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "detect: $repo is not a git work tree" >&2
  exit 2
fi

# Pathspecs keep this glob-safe; :(exclude) drops vendored trees and the headers
# that declare the helpers themselves.
pathspec=(
  '*.cxx' '*.cpp' '*.hxx' '*.h'
  ':(exclude)*ThirdParty*'
  ':(exclude)*itkImageFileReader.h'
  ':(exclude)*itkImageFileWriter.h'
)

pattern='itk::ImageFile(Reader|Writer)<'

hits="$(git grep -nE "$pattern" -- "${pathspec[@]}" 2>/dev/null)"

count=0
if [ -n "$hits" ]; then
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    count=$((count + 1))
    file="${line%%:*}"
    rest="${line#*:}"
    lno="${rest%%:*}"
    echo "=== $file:$lno"
    # Context window: the chain is typically within ~7 lines below the using/New.
    start=$lno
    end=$((lno + 7))
    git grep -nE "$pattern" -- "$file" >/dev/null 2>&1
    awk -v s="$start" -v e="$end" 'NR>=s && NR<=e { printf "  %d: %s\n", NR, $0 }' "$file"
  done <<< "$hits"
fi

echo
echo "candidate declarations: $count"
[ "$count" -gt 0 ] && exit 0 || exit 1
