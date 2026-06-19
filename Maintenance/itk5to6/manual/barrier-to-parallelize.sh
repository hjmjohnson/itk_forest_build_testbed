#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../lib" && pwd)/migrate_common.sh"
TASK_NAME="barrier-to-parallelize"; TASK_LEVEL="manual"
GREP_PATTERN='itk::Barrier'
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  mc_report_only \
    "itk::Barrier has moved to the ITKDeprecated module and will be removed in ITKv6. Restructure the algorithm to use itk::MultiThreaderBase::ParallelizeImageRegion with a lambda — each lambda invocation is independent and barriers are not needed. If synchronisation is genuinely required, use std::barrier (C++20) or a condition variable."
fi
