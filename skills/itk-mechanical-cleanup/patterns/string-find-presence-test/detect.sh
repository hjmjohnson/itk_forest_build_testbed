#!/usr/bin/env bash
# Detect the legacy substring-presence idiom  str.find(sub) < str.(length|size)()
# in ITK-ecosystem C++ sources.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../../lib/detect-common.sh"

PATTERN='\.find\([^)]*\)[[:space:]]*<[[:space:]]*[A-Za-z_][A-Za-z0-9_.]*\.(length|size)\(\)'

itk_detect_init "${1:-.}"

hits="$(itk_detect_grep "$PATTERN" "${ITK_DETECT_SOURCES[@]}")"
[ -n "$hits" ] && printf '%s\n' "$hits"

itk_detect_report "$(itk_detect_count "$hits")"
