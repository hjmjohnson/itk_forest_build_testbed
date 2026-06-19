#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../lib" && pwd)/migrate_common.sh"
TASK_NAME="verify-const-qualifier"; TASK_LEVEL="manual"
GREP_PATTERN='(VerifyPreconditions|VerifyInputInformation)'
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  mc_report_only \
    "ITKv5+ declares VerifyPreconditions() and VerifyInputInformation() as const methods. Add 'const' to each override: 'void VerifyPreconditions() const override' and 'void VerifyInputInformation() const override'. If the code must remain compatible with ITKv4, guard with '#ifdef ITKv5_CONST' or equivalent. Missing const causes a compiler error when overriding a const virtual."
fi
