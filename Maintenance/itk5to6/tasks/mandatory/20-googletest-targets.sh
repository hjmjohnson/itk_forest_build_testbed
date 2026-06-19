#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="googletest-targets"; TASK_LEVEL="mandatory"
MC_FILE_GLOB='*.cmake CMakeLists.txt'
GREP_PATTERN='GTest::(GTest|Main)'
SED_EXPRS=('s/GTest::GTest/GTest::gtest/g' 's/GTest::Main/GTest::gtest_main/g')
read -r -d '' COMMIT_MSG <<'EOF' || true
COMP: Use lowercase GoogleTest imported targets (GTest::gtest / GTest::gtest_main)

ITKv6's bundled GoogleTest exports lowercase target names (GTest::gtest,
GTest::gtest_main) matching upstream CMake convention since CMake 3.20.
The old capitalized aliases GTest::GTest and GTest::Main are no longer
available and cause link errors.
EOF
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_text_substitution_task
fi
