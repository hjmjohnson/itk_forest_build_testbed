#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="doxygen-itkref"; TASK_LEVEL="prep-v5"
# Single-quoted \\ reaches git grep -E as a literal backslash, matching \doxygen{ in source files.
GREP_PATTERN='\\(sub)?doxygen\{'
SED_EXPRS=('s/\\doxygen{/\\itkref{/g' 's/\\subdoxygen{/\\itksubref{/g')
COMMIT_MSG="DOC: Update \\doxygen / \\subdoxygen aliases to \\itkref / \\itksubref

ITKv6 renames the Doxygen aliases. \\itkref{} and \\itksubref{} are the
ITKv6 spellings; the old aliases no longer resolve."
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_text_substitution_task
fi
