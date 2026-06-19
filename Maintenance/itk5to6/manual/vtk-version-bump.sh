#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../lib" && pwd)/migrate_common.sh"
TASK_NAME="vtk-version-bump"; TASK_LEVEL="manual"
MC_FILE_GLOB='*.cmake CMakeLists.txt'
GREP_PATTERN='find_package\(VTK 8'
RESIDUAL_PATTERN='find_package\(VTK 8'
SED_EXPRS=(
  's/find_package(VTK 8[0-9.]*/find_package(VTK 9.1/g'
)
read -r -d '' COMMIT_MSG <<'EOF' || true
COMP: Raise VTK minimum version to 9.1 (ITKv5→v6)

Updates find_package(VTK 8.x...) calls to require VTK 9.1, which is
the minimum version supported by ITKv6.

Note: VTK 9.1 is available in most major Linux distributions released
in 2022 or later (Ubuntu 22.04, RHEL 9, Fedora 36+). If your
distribution ships an older VTK, build VTK 9.1+ from source or use
the Kitware APT/YUM repository.
EOF
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_regex_review_task
fi
