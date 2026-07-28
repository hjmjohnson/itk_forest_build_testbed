#!/usr/bin/env bash
# Apply readability-container-size-empty via clang-tidy.
# Dry-run by default; pass --apply to write. Never commits.
#   transform.sh <repo> <build-dir> [--apply]
set -uo pipefail

repo="${1:-}"
build="${2:-}"
apply=""
[ "${3:-}" = "--apply" ] && apply="1"

if [ -z "$repo" ] || [ -z "$build" ]; then
  echo "usage: transform.sh <repo> <build-dir> [--apply]" >&2
  exit 2
fi
if [ ! -f "$build/compile_commands.json" ]; then
  echo "error: $build/compile_commands.json not found (configure with" \
       "CMAKE_EXPORT_COMPILE_COMMANDS=ON)" >&2
  exit 2
fi
command -v clang-tidy >/dev/null 2>&1 || { echo "error: clang-tidy not on PATH" >&2; exit 2; }

pattern='\.(size|length)\(\)[[:space:]]*(([=!]=|<=|>=?)[[:space:]]*0|(<|>=)[[:space:]]*1)\b'
mapfile -t files < <(git -C "$repo" grep -lE "$pattern" -- \
                       ':!*ThirdParty*' ':!*thirdparty*' 2>/dev/null)

if [ "${#files[@]}" -eq 0 ]; then
  echo "no candidate files found"
  exit 0
fi

# git grep paths are repo-relative; make them absolute for clang-tidy.
abs=()
for f in "${files[@]}"; do abs+=("$repo/$f"); done

echo "candidate files: ${#abs[@]}"
fix_flag="--export-fixes=/dev/stdout"
[ -n "$apply" ] && fix_flag="-fix"

clang-tidy -p "$build" -checks='-*,readability-container-size-empty' \
  "$fix_flag" "${abs[@]}"

if [ -z "$apply" ]; then
  echo "----"
  echo "dry-run: proposed fixes printed above. Re-run with --apply to write."
fi
