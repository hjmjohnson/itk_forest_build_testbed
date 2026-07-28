#!/usr/bin/env bash
# Find image-iterator construction sites with redundant explicit template args
# that C++17 CTAD can deduce: <IterName><...>( where first arg is an image.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../../lib/detect-common.sh"

ITERS='ImageRegionConstIteratorWithIndex|ImageRegionIteratorWithIndex|ImageRegionConstIterator|ImageRegionIterator|ImageScanlineConstIterator|ImageScanlineIterator|ImageRegionRange|ImageBufferRange'
PATTERN="(${ITERS})<[^>;]+>[[:space:]]*\("

itk_detect_init "${1:-.}"

hits="$(itk_detect_grep "$PATTERN" "${ITK_DETECT_SOURCES[@]}")"
[ -n "$hits" ] && printf '%s\n' "$hits"

itk_detect_report "$(itk_detect_count "$hits")"
