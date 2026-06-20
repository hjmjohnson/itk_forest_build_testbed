#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="disallow-copy-and-move"; TASK_LEVEL="legacy-remove"
MC_FILE_GLOB='*.h *.hxx *.hpp *.txx *.cxx *.cpp *.cc *.c'
GREP_PATTERN='ITK_DISALLOW_COPY_AND_ASSIGN'
SED_EXPRS=('s/ITK_DISALLOW_COPY_AND_ASSIGN/ITK_DISALLOW_COPY_AND_MOVE/g')
read -r -d '' COMMIT_MSG <<'EOF' || true
STYLE: Rename ITK_DISALLOW_COPY_AND_ASSIGN to ITK_DISALLOW_COPY_AND_MOVE

Clarifies that the macro does not just disallow copy and assign, but also
move operations. In this context 'move' refers to both move-construct and
move-assign. The old macro name remains available unless
ITK_FUTURE_LEGACY_REMOVE is enabled.
EOF
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_text_substitution_task
fi
