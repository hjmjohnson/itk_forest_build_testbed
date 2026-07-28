#!/usr/bin/env bash
# List the cleanup patterns this skill exposes: every patterns/<name>/ that
# carries a detect.sh. One pattern name per line, sorted.
# Exit 0 if at least one is found, 1 otherwise.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
names=()
for d in "$here"/patterns/*/; do
    [ -f "${d}detect.sh" ] || continue
    names+=("$(basename "$d")")
done
[ "${#names[@]}" -gt 0 ] || exit 1
printf '%s\n' "${names[@]}" | sort
