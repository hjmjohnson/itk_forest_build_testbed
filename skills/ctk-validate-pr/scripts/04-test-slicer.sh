#!/usr/bin/env bash
# Run Slicer CTest suite.
# Usage: 04-test-slicer.sh [<slicer_bld_dir>] [<display>]
# Output: test log + JUnit XML at <slicer_bld_dir>/validate-slicer-test-*
#         machine-readable summary at <slicer_bld_dir>/validate-slicer-test-summary.txt
# Exit code: always 0 (failures are reported, not fatal)
set -uo pipefail

SLICER_BLD="${1:-$HOME/src/Slicer-bld}"
DISPLAY_VAR="${2:-${DISPLAY:-:0}}"
SLICER_INNER="${SLICER_BLD}/Slicer-build"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
TEST_LOG="${SLICER_BLD}/validate-slicer-test-${TIMESTAMP}.log"
JUNIT_XML="${SLICER_BLD}/validate-slicer-test-${TIMESTAMP}.xml"

if [ ! -d "${SLICER_INNER}" ]; then
  echo "FAIL: Slicer inner build directory does not exist: ${SLICER_INNER}"
  exit 0
fi

echo "=== Testing Slicer (${SLICER_INNER}) ==="
echo "Log: ${TEST_LOG}"
echo ""

DISPLAY="${DISPLAY_VAR}" ctest --test-dir "${SLICER_INNER}" \
  --timeout 120 \
  --output-on-failure \
  --output-junit "${JUNIT_XML}" \
  -E "SlicerApp-Test" \
  2>&1 | tee "${TEST_LOG}"

# Parse results (use || true to prevent pipefail from killing us on no-match)
SUMMARY_LINE=$({ grep -E '^[0-9]+% tests passed' "${TEST_LOG}" || true; })
TOTAL=$(echo "${SUMMARY_LINE}" | { grep -oE 'of [0-9]+' || true; } | { grep -oE '[0-9]+' || echo 0; })
FAILED_COUNT=$(echo "${SUMMARY_LINE}" | { grep -oE '[0-9]+ tests? failed' || true; } | { grep -oE '^[0-9]+' || echo 0; })
PASSED_COUNT=$((TOTAL - FAILED_COUNT))

# Extract failed test lines
FAILURES=$({ grep -E '^\s+[0-9]+ - .*(Failed|SEGFAULT|Timeout|Subprocess aborted)' "${TEST_LOG}" || true; })

# Classify failures as CTK-related or Slicer-own.
# CTK-related: test names containing DICOM, CTK, PythonQt, or ctk (case-insensitive)
CTK_FAILURES=$(echo "${FAILURES}" | { grep -iE 'DICOM|CTK|PythonQt' || true; })
SLICER_OWN_FAILURES=$(echo "${FAILURES}" | { grep -ivE 'DICOM|CTK|PythonQt' || true; })
CTK_FAILURE_COUNT=$(echo "${CTK_FAILURES}" | { grep -c '[^ ]' || true; })
SLICER_OWN_FAILURE_COUNT=$(echo "${SLICER_OWN_FAILURES}" | { grep -c '[^ ]' || true; })

# Write machine-readable summary
# Use unique delimiters for each block to avoid conflicts
cat > "${SLICER_BLD}/validate-slicer-test-summary.txt" <<EOSUMMARY
TOTAL=${TOTAL}
PASSED=${PASSED_COUNT}
FAILED=${FAILED_COUNT}
CTK_FAILURE_COUNT=${CTK_FAILURE_COUNT}
SLICER_OWN_FAILURE_COUNT=${SLICER_OWN_FAILURE_COUNT}
LOG=${TEST_LOG}
JUNIT=${JUNIT_XML}
FAILURES<<ENDBLOCK_FAILURES
${FAILURES}
ENDBLOCK_FAILURES
CTK_FAILURES<<ENDBLOCK_CTK
${CTK_FAILURES}
ENDBLOCK_CTK
SLICER_OWN_FAILURES<<ENDBLOCK_OWN
${SLICER_OWN_FAILURES}
ENDBLOCK_OWN
EOSUMMARY

echo ""
echo "SLICER TEST SUMMARY: ${PASSED_COUNT}/${TOTAL} passed, ${FAILED_COUNT} failed (CTK-related: ${CTK_FAILURE_COUNT}, Slicer-own: ${SLICER_OWN_FAILURE_COUNT})"
echo "Log: ${TEST_LOG}"
echo "JUnit: ${JUNIT_XML}"
echo "Summary: ${SLICER_BLD}/validate-slicer-test-summary.txt"
