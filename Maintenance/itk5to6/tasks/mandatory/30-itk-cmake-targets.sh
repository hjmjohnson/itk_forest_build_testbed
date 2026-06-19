#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="itk-cmake-targets"; TASK_LEVEL="mandatory"
MC_FILE_GLOB='*.cmake CMakeLists.txt'
GREP_PATTERN='\$\{ITK_LIBRARIES\}|ITK_USE_FILE'
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  mc_report_only \
    'Replace the ITK_LIBRARIES variable and include(ITK_USE_FILE) with namespaced ITK::<Module> targets; run WhatModulesITK.py (ITK/Utilities/Maintenance/WhatModulesITK.py) to enumerate the modules each target needs.'
fi
