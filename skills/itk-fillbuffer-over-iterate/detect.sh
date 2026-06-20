#!/usr/bin/env bash
# Find candidate iterator fill loops that could become image->FillBuffer(C).
# Over-reports by design: every hit must be read to confirm a full-buffer,
# loop-invariant constant fill with an unused index. Excludes ThirdParty/.
set -uo pipefail

REPO="${1:-.}"
cd "$REPO" || { echo "no such dir: $REPO" >&2; exit 2; }

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "not a git repo: $REPO (detect.sh uses git grep)" >&2
  exit 2
fi

# Pathspecs: C/C++ sources, exclude ThirdParty trees.
PATHS=(
  '*.h' '*.hxx' '*.cxx' '*.cpp' '*.cc' '*.txx'
  ':(exclude)*ThirdParty/*'
  ':(exclude)*/ThirdParty/*'
)

# Files that declare an ImageRegion iterator type.
iter_files="$(git grep -lE 'ImageRegion(Const)?Iterator(WithIndex)?' -- "${PATHS[@]}" 2>/dev/null)"

count=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  # Single-argument constant-assignment lines: it.Set(x) or *it = x;
  hits="$(grep -nE '\.Set\([^,)]+\)|\*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=[^=]' "$f" 2>/dev/null)"
  [ -n "$hits" ] || continue
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    printf '%s:%s\n' "$f" "$line"
    count=$((count + 1))
  done <<EOF
$hits
EOF
done <<EOF
$iter_files
EOF

echo "----"
echo "candidate lines: $count"
echo "(review each: confirm full buffered/largest region + loop-invariant value + unused index)"
