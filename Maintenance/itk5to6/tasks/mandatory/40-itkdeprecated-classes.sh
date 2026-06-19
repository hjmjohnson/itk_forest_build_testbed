#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="itkdeprecated-classes"; TASK_LEVEL="mandatory"
GREP_PATTERN='itk::(TreeNode|Barrier|VectorResampleImageFilter|AtomicInt|SimpleFastMutexLock)'
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  mc_report_only \
    'Replace deprecated ITK classes: Barrier->ParallelizeImageRegion (itk::ParallelizeImageRegion or TBB), AtomicInt->std::atomic<T>, SimpleFastMutexLock->std::mutex, TreeNode->remove usage (no direct replacement; restructure data), VectorResampleImageFilter->ResampleImageFilter (supports vector images natively in ITKv6).'
fi
