#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../lib" && pwd)/migrate_common.sh"
TASK_NAME="cmake-cxx-floor"; TASK_LEVEL="manual"
MC_FILE_GLOB='*.cmake CMakeLists.txt'
GREP_PATTERN='CMAKE_CXX_STANDARD|cmake_minimum_required'
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  mc_report_only \
    "SUGGESTED (not required): ITKv6 requires C++17 and CMake >= 3.16.3. Review each site: (1) CMAKE_CXX_STANDARD — raise to 17 if below; (2) cmake_minimum_required — raise to the ITK floor (3.16.3) if below. WARNING: CMake minimum version changes have inter-project implications in SuperBuild or ExternalProject scenarios — coordinate with downstream consumers before bumping."
fi
