#!/usr/bin/env bash
# Detect one-shot itk::ImageFileReader/ImageFileWriter chains that could collapse
# to itk::ReadImage<I>(fn) / itk::WriteImage(src, fn). Review-only: prints
# file:line context for each declaration so a human confirms the New/SetFileName/
# Update chain. Arg $1 = repo path (default .).
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../lib/detect-common.sh"

PATTERN='itk::ImageFile(Reader|Writer)<'

itk_detect_init "${1:-.}"

# The headers that declare the helpers themselves are not call sites.
hits="$(itk_detect_grep "$PATTERN" "${ITK_DETECT_SOURCES[@]}" \
        ':(exclude)*itkImageFileReader.h' ':(exclude)*itkImageFileWriter.h')"

count=0
if [ -n "$hits" ]; then
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        count=$((count + 1))
        file="${line%%:*}"
        rest="${line#*:}"
        lno="${rest%%:*}"
        echo "=== $file:$lno"
        # Context window: the chain is typically within ~7 lines below the New.
        awk -v s="$lno" -v e="$((lno + 7))" \
            'NR>=s && NR<=e { printf "  %d: %s\n", NR, $0 }' "$file"
    done <<< "$hits"
fi

echo
itk_detect_report "$count" \
    '(review each: confirm the New/SetFileName/Update chain is a one-shot read or write)'
