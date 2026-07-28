#!/usr/bin/env bash
# Rewrite `T::Pointer x = T::New();` -> `auto x = T::New();` and
# `const FooPointer x = T::New();` -> `const auto x = T::New();`.
# Backreference-guarded (Form A), single-line only. Dry-run by default; --apply
# writes in place. Never commits. Re-run clang-format afterward.
set -uo pipefail

REPO="."
APPLY=0
for a in "$@"; do
    case "$a" in
        --apply) APPLY=1 ;;
        *) REPO="$a" ;;
    esac
done

cd "$REPO" || { echo "not a directory: $REPO" >&2; exit 2; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    echo "not a git work tree: $REPO" >&2; exit 2; }

PATHSPECS=(
    '*.cxx' '*.hxx' '*.h' '*.cpp' '*.cc' '*.txx'
    ':(exclude)*ThirdParty/*'
    ':(exclude)*/ThirdParty/*'
)

RE_PTR='([A-Za-z_][A-Za-z0-9_:<>, ]*)::Pointer[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*\1::New[[:space:]]*\([[:space:]]*\)'
RE_ALIAS='const[[:space:]]+([A-Za-z_][A-Za-z0-9_]*Pointer)[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*([A-Za-z_][A-Za-z0-9_:<>, ]*)::New[[:space:]]*\([[:space:]]*\)'

# Perl substitutions: preserve a leading const on Form A; emit const auto for B.
perl_fix() {
    perl -0777 -pe '
        s/(^|[\s{};])(?:typename\s+)?(const\s+)?([A-Za-z_][A-Za-z0-9_:<>, ]*)::Pointer\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\3::New\s*\(\s*\)/"$1".($2?"const ":"")."auto $4 = $3::New()"/mge;
        s/(^|[\s{};])const\s+[A-Za-z_][A-Za-z0-9_]*Pointer\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z_][A-Za-z0-9_:<>, ]*)::New\s*\(\s*\)/"$1"."const auto $2 = $3::New()"/mge;
    '
}

# Drop function-local `using FooPointer = T::Pointer;` (and typedef form) aliases
# that this rewrite just orphaned: rewriting their sole use to `auto` leaves a
# dead alias GCC flags as -Wunused-local-typedefs (the PR #608 regression).
# Conservative — only indented (function-local) Pointer-named aliases whose name
# occurs exactly once in the file (its own definition).
sweep_orphans() {
    perl -0777 -pe '
        my @names;
        push @names, $1 while /^[ \t]+(?:typename\s+)?using\s+(\w*Pointer)\s*=\s*[^;\n]*::Pointer\s*;[ \t]*\n/mg;
        push @names, $1 while /^[ \t]+typedef\s+[^;\n]*::Pointer\s+(\w*Pointer)\s*;[ \t]*\n/mg;
        for my $n (@names) {
            my $cnt = () = /\b\Q$n\E\b/g;
            next if $cnt != 1;
            s/^[ \t]+(?:typename\s+)?using\s+\Q$n\E\s*=\s*[^;\n]*::Pointer\s*;[ \t]*\n//mg;
            s/^[ \t]+typedef\s+[^;\n]*::Pointer\s+\Q$n\E\s*;[ \t]*\n//mg;
        }
    '
}

FILES="$( { git grep -lE "$RE_PTR" -- "${PATHSPECS[@]}" 2>/dev/null
            git grep -lE "$RE_ALIAS" -- "${PATHSPECS[@]}" 2>/dev/null; } \
          | sort -u | sed '/^$/d')"

[ -z "$FILES" ] && { echo "no candidate files"; exit 0; }

CHANGED=0
while IFS= read -r f; do
    [ -z "$f" ] && continue
    new="$(perl_fix < "$f" | sweep_orphans)"
    if [ "$new" != "$(cat "$f")" ]; then
        CHANGED=$((CHANGED+1))
        if [ "$APPLY" -eq 1 ]; then
            printf '%s' "$new" > "$f"
            echo "rewrote: $f"
        else
            echo "=== would change: $f ==="
            diff -u "$f" <(printf '%s' "$new") | sed -n '1,40p'
        fi
    fi
done <<< "$FILES"

echo "----------------------------------------"
if [ "$APPLY" -eq 1 ]; then
    echo "files rewritten: $CHANGED"
    echo "NOW RUN: pre-commit run clang-format --all-files   (or clang-format -i)"
else
    echo "files that would change: $CHANGED  (dry-run; pass --apply to write)"
fi
