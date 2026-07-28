#!/usr/bin/env bash
# Find constructor-style temporaries passed to push_back/push_front
# (emplace_back/emplace_front candidates).
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../lib/detect-common.sh"

# .push_back( / .push_front( / ->push_back( / ->push_front(
# immediately followed by an Uppercase constructor-style call.
PATTERN='(\.|->)(push_back|push_front)\([A-Z][A-Za-z0-9_:<>]*\('

itk_detect_init "${1:-.}"

hits="$(itk_detect_grep "$PATTERN" "${ITK_DETECT_SOURCES[@]}")"
[ -n "$hits" ] && printf '%s\n' "$hits"

itk_detect_report "$(itk_detect_count "$hits")"
