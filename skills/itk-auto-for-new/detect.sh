#!/usr/bin/env bash
# Find ITK smart-pointer boilerplate: `T::Pointer x = T::New();` (backreference
# guarded so LHS type == RHS factory type) and the `const FooPointer x =
# FooType::New();` alias form. Glob-safe via git grep pathspecs; ThirdParty
# excluded. Prints file:line hits + counts.
set -uo pipefail

REPO="${1:-.}"
cd "$REPO" || { echo "not a directory: $REPO" >&2; exit 2; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    echo "not a git work tree: $REPO" >&2; exit 2; }

PATHSPECS=(
    '*.cxx' '*.hxx' '*.h' '*.cpp' '*.cc' '*.txx'
    ':(exclude)*ThirdParty/*'
    ':(exclude)*/ThirdParty/*'
)

# Form A: <Type>::Pointer name = <same Type>::New();   (\1 backreference)
RE_PTR='([A-Za-z_][A-Za-z0-9_:<>, ]*)::Pointer[[:space:]]+[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=[[:space:]]*\1::New[[:space:]]*\([[:space:]]*\)'

# Form B: const <Alias>Pointer name = <Type>::New();   (alias LHS, eyeball form)
RE_ALIAS='const[[:space:]]+[A-Za-z_][A-Za-z0-9_]*Pointer[[:space:]]+[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=[[:space:]]*[A-Za-z_][A-Za-z0-9_:<>, ]*::New[[:space:]]*\([[:space:]]*\)'

echo "== Form A: T::Pointer x = T::New()  (backreference-guarded, safe auto) =="
A_OUT="$(git grep -nE "$RE_PTR" -- "${PATHSPECS[@]}" 2>/dev/null)"
[ -n "$A_OUT" ] && printf '%s\n' "$A_OUT"
A_COUNT="$(printf '%s' "$A_OUT" | grep -c . )"

echo
echo "== Form B: const <Alias>Pointer x = T::New()  (alias LHS, review first) =="
B_OUT="$(git grep -nE "$RE_ALIAS" -- "${PATHSPECS[@]}" 2>/dev/null)"
[ -n "$B_OUT" ] && printf '%s\n' "$B_OUT"
B_COUNT="$(printf '%s' "$B_OUT" | grep -c . )"

echo
echo "----------------------------------------"
echo "Form A (safe auto) matches : $A_COUNT"
echo "Form B (alias, review)     : $B_COUNT"
echo "Total candidate sites      : $(( A_COUNT + B_COUNT ))"

[ "$(( A_COUNT + B_COUNT ))" -gt 0 ]
