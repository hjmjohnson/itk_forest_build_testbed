#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../lib" && pwd)/migrate_common.sh"
TASK_NAME="multithreader-backends"; TASK_LEVEL="manual"
GREP_PATTERN='SetNumberOfThreads|GetNumberOfThreads|ThreadInfoStruct'
RESIDUAL_PATTERN='SetNumberOfThreads|GetNumberOfThreads|ThreadInfoStruct'
SED_EXPRS=(
  's/SetNumberOfThreads/SetNumberOfWorkUnits/g'
  's/GetNumberOfThreads/GetNumberOfWorkUnits/g'
  's/ThreadInfoStruct/WorkUnitInfo/g'
)
read -r -d '' COMMIT_MSG <<'EOF' || true
ENH: Replace itk::MultiThreader work-unit API (ITKv5→v6)

Renames SetNumberOfThreads→SetNumberOfWorkUnits,
GetNumberOfThreads→GetNumberOfWorkUnits, and
ThreadInfoStruct→WorkUnitInfo mechanically.

Manual follow-up required:
- Choose PlatformMultiThreader vs PoolMultiThreader for your use case.
- Convert ThreadedGenerateData(region, threadId) to
  DynamicThreadedGenerateData(region), removing all threadId references.
  DynamicThreadedGenerateData does not receive a thread-id; for cross-thread
  synchronisation restructure with ParallelizeImageRegion (preferred) or
  std::barrier (C++20). Do not use itk::Barrier — it is deprecated and
  moved to ITKDeprecated.
EOF
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_regex_review_task
fi
