#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="getstaticconstmacro"; TASK_LEVEL="legacy-remove"
MC_FILE_GLOB='*.h *.hxx *.hpp *.txx *.cxx *.cpp *.cc *.c'
GREP_PATTERN='itkGetStaticConstMacro'
RESIDUAL_PATTERN='itkGetStaticConstMacro *\('
SED_EXPRS=('s/itkGetStaticConstMacro *(\(.*\))/Self::\1/g')
read -r -d '' COMMIT_MSG <<'EOF' || true
STYLE: Replace itkGetStaticConstMacro(name) with Self::name

The 'itkGetStaticConstMacro(name)' macro expands to 'Self::name'. Using
'Self::name' directly is clearer and does not depend on the macro.
The macro is removed when ITK_LEGACY_REMOVE is ON.
EOF
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_regex_review_task
fi
