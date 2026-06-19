#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../lib" && pwd)/migrate_common.sh"
TASK_NAME="python-cleanups"; TASK_LEVEL="manual"
GREP_PATTERN='itkConfig\.LazyLoading|LongDouble|\.image_from_array'
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  mc_report_only \
    "ITKv6 Python changes: (1) itkConfig.LazyLoading has been removed — delete all reads/writes of this attribute. (2) Long-double wrapping is dropped — remove any itk types or filters parameterised on LongDouble/long double. (3) itk.image_from_array() semantics changed — review .T (transpose) assumptions; the axis ordering convention was updated in ITKv5."
fi
