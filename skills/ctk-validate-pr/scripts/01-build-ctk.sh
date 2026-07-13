#!/usr/bin/env bash
# Build CTK inner build for a given Qt version.
# Usage: 01-build-ctk.sh <qt_version> [<ctk_source_dir>]
# Output: build log at <build_dir>/validate-build.log
# Exit code: 0 on success, 1 on failure
set -euo pipefail

QT_VER="${1:?Usage: $0 <qt_version> [<ctk_source_dir>]}"
CTK_SRC="${2:-$HOME/src/CTK}"
BLD_DIR="${CTK_SRC}/cmake-build-clazy-qt${QT_VER}/CTK-build"
LOG="${BLD_DIR}/validate-build.log"
NPROC=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 8)

if [ ! -d "${BLD_DIR}" ]; then
  echo "FAIL: Build directory does not exist: ${BLD_DIR}"
  echo "Run /clazy-configure first to set up the superbuild."
  exit 1
fi

echo "=== Building CTK Qt${QT_VER} (${BLD_DIR}) ==="
echo "Source: ${CTK_SRC}"
echo "Commit: $(cd "${CTK_SRC}" && git log --oneline -1 HEAD)"
echo "Log: ${LOG}"
echo ""

cmake --build "${BLD_DIR}" --parallel "${NPROC}" 2>&1 | tee "${LOG}"
BUILD_EXIT=${PIPESTATUS[0]}

ERRORS=$({ grep ' error:' "${LOG}" || true; } | wc -l | tr -d ' ')
WARNINGS=$({ grep ' warning:' "${LOG}" || true; } | { grep -v '\[-Wclazy' || true; } | wc -l | tr -d ' ')

echo ""
echo "BUILD SUMMARY Qt${QT_VER}: exit_code=${BUILD_EXIT} errors=${ERRORS} warnings=${WARNINGS}"
echo "Log: ${LOG}"

if [ "${BUILD_EXIT}" -ne 0 ] || [ "${ERRORS}" -gt 0 ]; then
  echo "FAIL: CTK Qt${QT_VER} build failed"
  echo "--- First errors ---"
  { grep ' error:' "${LOG}" || true; } | head -20
  exit 1
fi
