#!/usr/bin/env bash
# Apply clang-tidy modernize-use-emplace to a tree, then clang-format.
# Dry-run by default (lists candidate files); --apply writes fixes.
# Never commits.
set -uo pipefail

REPO="${1:-.}"
BUILD="${2:-}"
APPLY=0
for a in "$@"; do [ "$a" = "--apply" ] && APPLY=1; done

if [ -z "$BUILD" ] || [ "$BUILD" = "--apply" ]; then
  echo "usage: transform.sh <repo> <build-dir-with-compile_commands.json> [--apply]" >&2
  exit 2
fi
if [ ! -f "$BUILD/compile_commands.json" ]; then
  echo "error: $BUILD/compile_commands.json not found" >&2
  exit 2
fi
command -v clang-tidy >/dev/null 2>&1 || { echo "error: clang-tidy not found" >&2; exit 2; }

# Candidate files from the detector (same dir as this script).
HERE="$(cd "$(dirname "$0")" && pwd)"
files=$(bash "$HERE/detect.sh" "$REPO" 2>/dev/null \
  | grep -E '^[^:]+:[0-9]+:' | cut -d: -f1 | sort -u)

if [ -z "$files" ]; then
  echo "no candidate files found"
  exit 0
fi

echo "candidate files:"
printf '%s\n' "$files"

if [ "$APPLY" -ne 1 ]; then
  echo "----"
  echo "dry-run: re-run with --apply to fix and clang-format"
  exit 0
fi

echo "----"
while IFS= read -r f; do
  [ -n "$f" ] || continue
  path="$REPO/$f"
  [ -f "$path" ] || continue
  echo "clang-tidy: $f"
  clang-tidy -p "$BUILD" -checks='-*,modernize-use-emplace' -fix "$path" 2>/dev/null
  if command -v clang-format >/dev/null 2>&1; then
    clang-format -i "$path"
  fi
done <<< "$files"

echo "----"
echo "done. review with: git -C $REPO diff   (NOT committed)"
