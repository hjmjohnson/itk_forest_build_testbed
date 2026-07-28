#!/usr/bin/env bash
# Find ITK smart-pointer boilerplate: `T::Pointer x = T::New();` (backreference
# guarded so LHS type == RHS factory type) and the `const FooPointer x =
# FooType::New();` alias form. Prints file:line hits + per-form counts.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../lib/detect-common.sh"

# Form A: <Type>::Pointer name = <same Type>::New();   (\1 backreference)
RE_PTR='([A-Za-z_][A-Za-z0-9_:<>, ]*)::Pointer[[:space:]]+[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=[[:space:]]*\1::New[[:space:]]*\([[:space:]]*\)'

# Form B: const <Alias>Pointer name = <Type>::New();   (alias LHS, eyeball form)
RE_ALIAS='const[[:space:]]+[A-Za-z_][A-Za-z0-9_]*Pointer[[:space:]]+[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=[[:space:]]*[A-Za-z_][A-Za-z0-9_:<>, ]*::New[[:space:]]*\([[:space:]]*\)'

itk_detect_init "${1:-.}"

echo "== Form A: T::Pointer x = T::New()  (backreference-guarded, safe auto) =="
A_OUT="$(itk_detect_grep "$RE_PTR" "${ITK_DETECT_SOURCES[@]}")"
[ -n "$A_OUT" ] && printf '%s\n' "$A_OUT"
A_COUNT="$(itk_detect_count "$A_OUT")"

echo
echo "== Form B: const <Alias>Pointer x = T::New()  (alias LHS, review first) =="
B_OUT="$(itk_detect_grep "$RE_ALIAS" "${ITK_DETECT_SOURCES[@]}")"
[ -n "$B_OUT" ] && printf '%s\n' "$B_OUT"
B_COUNT="$(itk_detect_count "$B_OUT")"

echo
itk_detect_report "$(( A_COUNT + B_COUNT ))" \
    "Form A (safe auto) matches : ${A_COUNT}" \
    "Form B (alias, review)     : ${B_COUNT}"
