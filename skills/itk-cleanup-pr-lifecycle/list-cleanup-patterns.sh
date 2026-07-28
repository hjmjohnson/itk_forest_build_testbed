#!/usr/bin/env bash
# List the payloads eligible for itk-cleanup-pr-lifecycle / -incremental-refactor-loop:
#
#   itk-mechanical-cleanup:<pattern>   one per pattern that exposes a detect.sh
#   <skill>                            script-based multi-class refactor skills
#
# One payload per line, sorted. Exit 0 if at least one is found, 1 otherwise.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skills_root="$(dirname "$here")"
names=()

# Patterns owned by itk-mechanical-cleanup.
lister="$skills_root/itk-mechanical-cleanup/list-patterns.sh"
if [ -f "$lister" ]; then
    while IFS= read -r p; do
        [ -n "$p" ] && names+=("itk-mechanical-cleanup:$p")
    done < <(bash "$lister" 2>/dev/null)
fi

# Script-based refactor skills that enumerate their own pattern classes.
for s in itk-declare-then-init; do
    [ -f "$skills_root/$s/SKILL.md" ] && names+=("$s")
done

[ "${#names[@]}" -gt 0 ] || exit 1
printf '%s\n' "${names[@]}" | sort
