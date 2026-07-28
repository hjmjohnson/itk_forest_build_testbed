#!/usr/bin/env bash
# Find candidate iterator fill loops that could become image->FillBuffer(C).
# Over-reports by design: every hit must be read to confirm a full-buffer,
# loop-invariant constant fill with an unused index.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../lib/detect-common.sh"

itk_detect_init "${1:-.}"

# Files that declare an ImageRegion iterator type.
iter_files="$(git grep -lE 'ImageRegion(Const)?Iterator(WithIndex)?' \
              -- "${ITK_DETECT_SOURCES[@]}" "${ITK_DETECT_EXCLUDES[@]}" 2>/dev/null || true)"

count=0
while IFS= read -r f; do
    [ -n "$f" ] || continue
    # Single-argument constant-assignment lines: it.Set(x) or *it = x;
    hits="$(grep -nE '\.Set\([^,)]+\)|\*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=[^=]' "$f" 2>/dev/null)" || true
    [ -n "$hits" ] || continue
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        printf '%s:%s\n' "$f" "$line"
        count=$((count + 1))
    done <<< "$hits"
done <<< "$iter_files"

itk_detect_report "$count" \
    '(review each: confirm full buffered/largest region + loop-invariant value + unused index)'
