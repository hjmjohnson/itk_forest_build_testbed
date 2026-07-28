#!/usr/bin/env bash
# Detect hand-written empty-body special members that should be `= default`.
#   $1 = repo path (default: .)
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../../lib/detect-common.sh"

# In-class empty-body special member: Name(...) [override] {}  with empty {}.
# Heuristic: an identifier (optionally ~), a paren group, optional override,
# then "{}" (possibly spaced) optionally followed by ';'.
INCLASS_RE='(^|[[:space:]])~?[A-Za-z_][A-Za-z0-9_]*[[:space:]]*\([^)]*\)[[:space:]]*(override[[:space:]]*)?\{[[:space:]]*\}[[:space:]]*;?'

# Out-of-line empty destructor body on one line: T::~T(...) {}
OUTLINE_RE='[A-Za-z_][A-Za-z0-9_]*::~[A-Za-z_][A-Za-z0-9_]*[[:space:]]*\([^)]*\)[[:space:]]*\{[[:space:]]*\}'

itk_detect_init "${1:-.}"

# Drop: already-defaulted lines; non-empty bodies (anything but whitespace
# between the braces); and comment-block tails (line ends with */), which are
# the dominant false positives.
inclass="$(itk_detect_grep "$INCLASS_RE" "${ITK_DETECT_SOURCES[@]}" \
           | grep -vE '=[[:space:]]*default' \
           | grep -vE '\{[[:space:]]*[^}[:space:]]' \
           | grep -vE '\*/[[:space:]]*$')" || true
outline="$(itk_detect_grep "$OUTLINE_RE" "${ITK_DETECT_SOURCES[@]}")"

n_in="$(itk_detect_count "$inclass")"
n_out="$(itk_detect_count "$outline")"

if [ "$n_in" -gt 0 ]; then
    echo "== in-class empty-body special members ( {} -> = default ) =="
    printf '%s\n' "$inclass" | sed 's/^/  /'
fi
if [ "$n_out" -gt 0 ]; then
    echo "== out-of-line empty destructor bodies [out-of-line, review-only] =="
    printf '%s\n' "$outline" | sed 's/^/  /'
fi

echo
itk_detect_report "$(( n_in + n_out ))" \
    "in-class candidates : ${n_in}" \
    "out-of-line bodies  : ${n_out}"
