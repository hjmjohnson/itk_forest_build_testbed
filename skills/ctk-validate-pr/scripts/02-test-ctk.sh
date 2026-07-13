#!/usr/bin/env bash
# Run CTK CTest for a given Qt version.
# Usage: 02-test-ctk.sh <qt_version> [<ctk_source_dir>] [<display>]
# Output: test log + JUnit XML at <build_dir>/validate-test-*
#         machine-readable summary at <build_dir>/validate-test-summary-qt<ver>.txt
# Exit code: always 0 (failures are reported, not fatal)
set -uo pipefail

QT_VER="${1:?Usage: $0 <qt_version> [<ctk_source_dir>] [<display>]}"
CTK_SRC="${2:-$HOME/src/CTK}"
DISPLAY_VAR="${3:-${DISPLAY:-:0}}"
BLD_DIR="${CTK_SRC}/cmake-build-clazy-qt${QT_VER}/CTK-build"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
TEST_LOG="${BLD_DIR}/validate-test-${TIMESTAMP}.log"
JUNIT_XML="${BLD_DIR}/validate-test-${TIMESTAMP}.xml"

if [ ! -d "${BLD_DIR}" ]; then
  echo "FAIL: Build directory does not exist: ${BLD_DIR}"
  exit 0
fi

echo "=== Testing CTK Qt${QT_VER} (${BLD_DIR}) ==="
echo "Commit: $(cd "${CTK_SRC}" && git log --oneline -1 HEAD)"
echo "Log: ${TEST_LOG}"
echo ""

# Reconfigure to pick up any CMakeLists.txt changes
cmake --build "${BLD_DIR}" --target rebuild_cache > /dev/null 2>&1 || true

DISPLAY="${DISPLAY_VAR}" ctest --test-dir "${BLD_DIR}" \
  --timeout 60 \
  --output-on-failure \
  --output-junit "${JUNIT_XML}" \
  2>&1 | tee "${TEST_LOG}"

# Parse results
SUMMARY_LINE=$({ grep -E '^[0-9]+% tests passed' "${TEST_LOG}" || true; })
TOTAL=$(echo "${SUMMARY_LINE}" | { grep -oE 'of [0-9]+' || true; } | { grep -oE '[0-9]+' || echo 0; })
FAILED_COUNT=$(echo "${SUMMARY_LINE}" | { grep -oE '[0-9]+ tests? failed' || true; } | { grep -oE '^[0-9]+' || echo 0; })
PASSED_COUNT=$((TOTAL - FAILED_COUNT))
DISABLED_COUNT=$({ grep -c '(Disabled)' "${TEST_LOG}" || true; })

# Extract failed test lines
FAILURES=$({ grep -E '^\s+[0-9]+ - .*(Failed|SEGFAULT|Timeout|Subprocess aborted)' "${TEST_LOG}" || true; })

# Write machine-readable summary
SUMMARY_FILE="${BLD_DIR}/validate-test-summary-qt${QT_VER}.txt"
cat > "${SUMMARY_FILE}" <<EOSUMMARY
QT_VERSION=${QT_VER}
TOTAL=${TOTAL}
PASSED=${PASSED_COUNT}
FAILED=${FAILED_COUNT}
DISABLED=${DISABLED_COUNT}
LOG=${TEST_LOG}
JUNIT=${JUNIT_XML}
FAILURES<<ENDBLOCK_FAILURES
${FAILURES}
ENDBLOCK_FAILURES
EOSUMMARY

echo ""
echo "TEST SUMMARY Qt${QT_VER}: ${PASSED_COUNT}/${TOTAL} passed, ${FAILED_COUNT} failed, ${DISABLED_COUNT} disabled"
echo "Log: ${TEST_LOG}"
echo "JUnit: ${JUNIT_XML}"
echo "Summary: ${SUMMARY_FILE}"
