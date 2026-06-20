#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="itktypemacro"; TASK_LEVEL="legacy-remove"
MC_FILE_GLOB='*.h *.hxx *.hpp *.txx *.cxx *.cpp *.cc *.c'
GREP_PATTERN='itkTypeMacro *\('
RESIDUAL_PATTERN='itkTypeMacro *\('
SED_EXPRS=('s/itkTypeMacro *(\(.*\),.*) *;/itkOverrideGetNameOfClassMacro(\1);/g')
read -r -d '' COMMIT_MSG <<'EOF' || true
STYLE: Add itkVirtualGetNameOfClassMacro + itkOverrideGetNameOfClassMacro

Added two new macros, intended to replace the old 'itkTypeMacro' and
'itkTypeMacroNoParent'. The aim is to be clearer about what they do: add
a virtual 'GetNameOfClass()' member function and override it. Unlike
'itkTypeMacro', 'itkOverrideGetNameOfClassMacro' has no 'superclass'
parameter, which was never used. Removed when ITK_LEGACY_REMOVE is ON.
EOF
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_regex_review_task
fi
