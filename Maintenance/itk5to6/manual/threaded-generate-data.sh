#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../lib" && pwd)/migrate_common.sh"
TASK_NAME="threaded-generate-data"; TASK_LEVEL="manual"
GREP_PATTERN='ThreadedGenerateData'
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  mc_report_only \
    "Convert ThreadedGenerateData(const OutputImageRegionType& region, itk::ThreadIdType threadId) to DynamicThreadedGenerateData(const OutputImageRegionType& region), removing all threadId references. If your algorithm requires cross-thread synchronisation or barriers, keep PlatformMultiThreader and implement with itk::Barrier or refactor to itk::MultiThreaderBase::ParallelizeImageRegion. See https://itk.org/migrationguide/ITKMigration-ITKv5.html#threadingmodel"
fi
