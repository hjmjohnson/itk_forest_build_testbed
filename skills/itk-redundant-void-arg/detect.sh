#!/usr/bin/env bash
# Find redundant (void) parameter lists in C++ sources.
# Usage: detect.sh [repo-path]   (default: .)
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../lib/detect-common.sh"

# identifier (possibly qualified/templated/dtor) immediately followed by (void)
PATTERN='[A-Za-z_~][A-Za-z0-9_:<>~]*[[:space:]]*\([[:space:]]*void[[:space:]]*\)'

itk_detect_init "${1:-.}"

hits="$(itk_detect_grep "$PATTERN" "${ITK_DETECT_SOURCES[@]}")"
[ -n "$hits" ] && printf '%s\n' "$hits"

itk_detect_report "$(itk_detect_count "$hits")" \
    '(function-pointer typedefs / extern "C" are false positives; clang-tidy is the arbiter)'
