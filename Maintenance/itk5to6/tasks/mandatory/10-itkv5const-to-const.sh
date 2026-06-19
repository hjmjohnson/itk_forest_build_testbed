#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="itkv5const-to-const"; TASK_LEVEL="mandatory"
GREP_PATTERN='ITKv5_CONST'
SED_EXPRS=('s/ITKv5_CONST/const/g')
read -r -d '' COMMIT_MSG <<'EOF' || true
ENH: Replace ITKv5_CONST with const

ITKv5_CONST bridged the const-qualifier added to ProcessObject::
VerifyPreconditions() and VerifyInputInformation() in ITKv5 while keeping
ITKv4 compilable. ITKv6 removes ITKV4_COMPATIBILITY and the macro, so the
const qualifier is now unconditional.
EOF
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_text_substitution_task
fi
