#!/usr/bin/env bash
# Find discarded-value postfix increment/decrement sites that should be prefix.
# Two shapes only:
#   1. standalone statement:   IDENT++;   IDENT--;
#   2. for-increment clause:    for(...; ...; IDENT++)   IDENT--)
# Value-consuming postfix (a[i++], *p++, x=it++) is NOT matched.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../lib/detect-common.sh"

# Shape 1: an identifier immediately followed by ++ or -- that is the whole
# statement (optional leading whitespace, terminating ';'). Excludes a[i]++;
# style by requiring the token before ++/-- to be a bare identifier at stmt start.
RE_STMT='^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*(\+\+|--)[[:space:]]*;[[:space:]]*$'

# Shape 2: for-increment clause — a for header whose 3rd clause ends IDENT++)
# (or --). Requires two ';' inside the for(...) before the IDENT++/-- token.
RE_FOR='for[[:space:]]*\([^;]*;[^;]*;[^;()]*[A-Za-z_][A-Za-z0-9_]*(\+\+|--)[[:space:]]*\)'

itk_detect_init "${1:-.}"

hits="$(
    itk_detect_grep "$RE_STMT" "${ITK_DETECT_SOURCES[@]}"
    itk_detect_grep "$RE_FOR" "${ITK_DETECT_SOURCES[@]}"
)"
hits="$(printf '%s\n' "$hits" | grep -vE '^$' | sort -u)" || true
[ -n "$hits" ] && printf '%s\n' "$hits"

itk_detect_report "$(itk_detect_count "$hits")"
