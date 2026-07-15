#!/usr/bin/env bash
# List cleanup pattern skills eligible as itk-cleanup-pr-lifecycle payloads:
# every skills/itk-*/ that exposes a detect.sh. One skill name per line, sorted.
# Exit 0 if at least one is found, 1 otherwise.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skills_root="$(dirname "$here")"
names=()
for d in "$skills_root"/itk-*/; do
  name="$(basename "$d")"
  [ "$name" = "itk-cleanup-pr-lifecycle" ] && continue
  [ -f "${d}detect.sh" ] || continue
  names+=("$name")
done
printf '%s\n' "${names[@]}" | sort
[ "${#names[@]}" -gt 0 ]
