#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="cmake-lowercase"; TASK_LEVEL="prep-v5"
MC_FILE_GLOB='*.cmake CMakeLists.txt'
GREP_PATTERN='[A-Z_]{2,}\s*\('
COMMIT_MSG="STYLE: Lowercase CMake commands

Ancient CMake versions required upper-case commands. Later command names
became case-insensitive. Now the preferred style is lower-case."
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  SED_EXPRS=()
  while IFS= read -r cmd; do
    upper="$(printf '%s' "$cmd" | tr '[:lower:]' '[:upper:]')"
    SED_EXPRS+=("s/\\b${upper}\\(\\s*\\)(/${cmd}\\1(/g")
  done < <(cmake --help-command-list 2>/dev/null | grep -v "cmake version")
  if [ "${#SED_EXPRS[@]}" -eq 0 ]; then
    echo "[cmake-lowercase] cmake not found or no commands; skipping" >&2
    exit 0
  fi
  mc_init "$@"
  run_text_substitution_task
fi
