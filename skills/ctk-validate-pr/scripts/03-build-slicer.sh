#!/usr/bin/env bash
# Build Slicer against a specific CTK source directory.
# Usage: 03-build-slicer.sh [<ctk_source_dir>] [<slicer_bld_dir>]
#
# Prerequisites: Slicer superbuild must have been configured and built at least once.
#
# Architecture:
#   Slicer superbuild (~/src/Slicer-bld/)
#     -> CTK source checkout (~/src/Slicer-bld/CTK/)
#     -> CTK superbuild    (~/src/Slicer-bld/CTK-build/)
#     -> CTK inner build   (~/src/Slicer-bld/CTK-build/CTK-build/)
#     -> Slicer inner build (~/src/Slicer-bld/Slicer-build/)
#
# This script:
#   1. Syncs the specified CTK source into Slicer's CTK checkout
#   2. Clean-builds CTK inner build within Slicer (to capture ALL warnings/errors)
#   3. Rebuilds Slicer inner build (incremental, to catch CTK API breakage)
#
# A clean CTK build is required because an incremental build would only show
# warnings for changed files, missing any new warnings introduced by header
# changes that affect unchanged .cpp files.
#
# Output: build logs at <slicer_bld_dir>/validate-slicer-ctk-build.log
#                       <slicer_bld_dir>/validate-slicer-build.log
#         summary at    <slicer_bld_dir>/validate-slicer-build-summary.txt
# Exit code: 0 on success, 1 on failure
set -euo pipefail

CTK_SRC="${1:-$HOME/src/CTK}"
SLICER_BLD="${2:-$HOME/src/Slicer-bld}"
SLICER_CTK_SRC="${SLICER_BLD}/CTK"
SLICER_CTK_SUPERBLD="${SLICER_BLD}/CTK-build"
SLICER_CTK_BLD="${SLICER_BLD}/CTK-build/CTK-build"
SLICER_INNER="${SLICER_BLD}/Slicer-build"
CTK_BUILD_LOG="${SLICER_BLD}/validate-slicer-ctk-build.log"
SLICER_BUILD_LOG="${SLICER_BLD}/validate-slicer-build.log"
NPROC=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 8)

# Validate directories exist
for DIR_CHECK in "${CTK_SRC}" "${SLICER_BLD}" "${SLICER_CTK_BLD}" "${SLICER_INNER}"; do
  if [ ! -d "${DIR_CHECK}" ]; then
    echo "FAIL: Required directory does not exist: ${DIR_CHECK}"
    exit 1
  fi
done

CTK_BRANCH=$(cd "${CTK_SRC}" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "detached")
CTK_HASH=$(cd "${CTK_SRC}" && git rev-parse --short HEAD)

echo "=== Building Slicer against CTK ${CTK_BRANCH} (${CTK_HASH}) ==="
echo "CTK source:       ${CTK_SRC}"
echo "Slicer build:     ${SLICER_BLD}"
echo "CTK inner build:  ${SLICER_CTK_BLD}"
echo "Slicer inner:     ${SLICER_INNER}"
echo ""

########################################################################
# Step 1: Sync CTK source into Slicer's CTK checkout
########################################################################
echo "--- Step 1: Syncing CTK source ---"
if [ -d "${SLICER_CTK_SRC}/.git" ]; then
  cd "${SLICER_CTK_SRC}"
  # Add the local CTK as a remote if not already present
  git remote get-url ctk-local > /dev/null 2>&1 || git remote add ctk-local "${CTK_SRC}"
  # Fetch all refs from the local CTK source
  git fetch ctk-local 2>&1
  # Branch tips alone miss a detached PR commit (pull/NNN/head is on no
  # local branch); fetch the source's current HEAD object explicitly.
  git fetch ctk-local HEAD 2>&1 || true
  # Get the full hash from the CTK source to use for checkout
  CTK_FULL_HASH=$(cd "${CTK_SRC}" && git rev-parse HEAD)
  if [ "${CTK_BRANCH}" = "detached" ] || [ "${CTK_BRANCH}" = "HEAD" ]; then
    # Detached HEAD: the commit was fetched as part of a branch's history.
    # Checkout directly by full hash (available after fetch --all).
    git checkout --detach "${CTK_FULL_HASH}" 2>&1
    echo "Checked out detached HEAD at ${CTK_HASH}"
  else
    git checkout -B "validate-${CTK_BRANCH}" "ctk-local/${CTK_BRANCH}" 2>&1
    echo "Checked out validate-${CTK_BRANCH} tracking ctk-local/${CTK_BRANCH}"
  fi
  cd "${CTK_SRC}"
else
  echo "WARNING: ${SLICER_CTK_SRC} is not a git repo. Copying source via rsync..."
  rsync -a --delete --exclude='.git' --exclude='cmake-build-*' "${CTK_SRC}/" "${SLICER_CTK_SRC}/"
fi
echo "CTK source synced: $(cd "${SLICER_CTK_SRC}" && git log --oneline -1 HEAD 2>/dev/null || echo 'rsync copy')"
echo ""

########################################################################
# Step 2: Clean-build CTK inner build within Slicer
########################################################################
echo "--- Step 2: Clean-building CTK inner build ---"
echo "Cleaning ${SLICER_CTK_BLD}..."
cmake --build "${SLICER_CTK_BLD}" --target clean 2>&1 > /dev/null || true

# After a clean, we must rebuild via the superbuild CTK target so that
# PythonQt wrapper generation (ctkWrapPythonQt.py) re-runs and regenerates
# the generated_cpp/org_commontk_*/ files. Building the inner build
# directly after clean would fail due to missing generated headers.
echo "Rebuilding CTK via superbuild target (handles PythonQt wrapper regeneration)..."
cd "${SLICER_BLD}"
# Remove CTK stamp files to force reconfigure after source sync
rm -f "${SLICER_BLD}/CTK-prefix/src/CTK-stamp/CTK-configure" 2>/dev/null || true
rm -f "${SLICER_BLD}/CTK-prefix/src/CTK-stamp/CTK-build" 2>/dev/null || true
rm -f "${SLICER_BLD}/CTK-prefix/src/CTK-stamp/CTK-done" 2>/dev/null || true

ninja CTK -j"${NPROC}" 2>&1 | tee "${CTK_BUILD_LOG}"
CTK_BUILD_EXIT=${PIPESTATUS[0]}

# Count errors/warnings safely (grep returns 1 on no match, which kills pipefail)
# Classify by source: CTK source code (*/CTK/) vs dependencies (PythonQt, Python, VTK, etc.)
CTK_ERRORS=$({ grep ' error:' "${CTK_BUILD_LOG}" || true; } | wc -l | tr -d ' ')
CTK_WARNINGS=$({ grep ' warning:' "${CTK_BUILD_LOG}" || true; } | { grep -v '\[-Wclazy' || true; } | wc -l | tr -d ' ')
CTK_SRC_ERRORS=$({ grep ' error:' "${CTK_BUILD_LOG}" || true; } | { grep '/CTK/' || true; } | wc -l | tr -d ' ')
CTK_SRC_WARNINGS=$({ grep ' warning:' "${CTK_BUILD_LOG}" || true; } | { grep -v '\[-Wclazy' || true; } | { grep '/CTK/' || true; } | wc -l | tr -d ' ')
CTK_DEP_ERRORS=$((CTK_ERRORS - CTK_SRC_ERRORS))
CTK_DEP_WARNINGS=$((CTK_WARNINGS - CTK_SRC_WARNINGS))

# List unique CTK source files with warnings
CTK_SRC_WARNING_FILES=$({ grep ' warning:' "${CTK_BUILD_LOG}" || true; } | { grep '/CTK/' || true; } | { grep -oE '^[^:]+' || true; } | sort -u)

echo ""
echo "CTK BUILD SUMMARY: exit_code=${CTK_BUILD_EXIT} errors=${CTK_ERRORS} (CTK src: ${CTK_SRC_ERRORS}, deps: ${CTK_DEP_ERRORS}) warnings=${CTK_WARNINGS} (CTK src: ${CTK_SRC_WARNINGS}, deps: ${CTK_DEP_WARNINGS})"
if [ -n "${CTK_SRC_WARNING_FILES}" ]; then
  echo "CTK source files with warnings:"
  echo "${CTK_SRC_WARNING_FILES}" | sed 's|^|  |'
fi
echo "Log: ${CTK_BUILD_LOG}"

if [ "${CTK_BUILD_EXIT}" -ne 0 ] || [ "${CTK_ERRORS}" -gt 0 ]; then
  echo "FAIL: CTK build within Slicer failed"
  echo "--- First errors ---"
  { grep ' error:' "${CTK_BUILD_LOG}" || true; } | head -20
  # Write partial summary before exiting
  cat > "${SLICER_BLD}/validate-slicer-build-summary.txt" <<EOSUMMARY
CTK_BRANCH=${CTK_BRANCH}
CTK_HASH=${CTK_HASH}
CTK_BUILD_EXIT=${CTK_BUILD_EXIT}
CTK_BUILD_ERRORS=${CTK_ERRORS}
CTK_BUILD_WARNINGS=${CTK_WARNINGS}
CTK_SRC_ERRORS=${CTK_SRC_ERRORS}
CTK_SRC_WARNINGS=${CTK_SRC_WARNINGS}
CTK_DEP_ERRORS=${CTK_DEP_ERRORS}
CTK_DEP_WARNINGS=${CTK_DEP_WARNINGS}
CTK_SRC_WARNING_FILES=${CTK_SRC_WARNING_FILES}
CTK_BUILD_LOG=${CTK_BUILD_LOG}
SLICER_BUILD_EXIT=N/A
SLICER_BUILD_ERRORS=N/A
SLICER_BUILD_WARNINGS=N/A
SLICER_BUILD_LOG=N/A
EOSUMMARY
  exit 1
fi
echo ""

########################################################################
# Step 3: Rebuild Slicer inner build (incremental)
########################################################################
echo "--- Step 3: Rebuilding Slicer inner build ---"

# Invalidate Slicer stamp files so it reconfigures against the freshly built CTK
rm -f "${SLICER_BLD}/Slicer-prefix/src/Slicer-stamp/Slicer-configure" 2>/dev/null || true
rm -f "${SLICER_BLD}/Slicer-prefix/src/Slicer-stamp/Slicer-build" 2>/dev/null || true
rm -f "${SLICER_BLD}/Slicer-prefix/src/Slicer-stamp/Slicer-done" 2>/dev/null || true

ninja Slicer -j"${NPROC}" 2>&1 | tee "${SLICER_BUILD_LOG}"
SLICER_BUILD_EXIT=${PIPESTATUS[0]}

SLICER_ERRORS=$({ grep ' error:' "${SLICER_BUILD_LOG}" || true; } | wc -l | tr -d ' ')
SLICER_WARNINGS=$({ grep ' warning:' "${SLICER_BUILD_LOG}" || true; } | wc -l | tr -d ' ')
# Slicer inner build warnings/errors from CTK headers (e.g. CTK-build/ paths)
SLICER_CTK_ERRORS=$({ grep ' error:' "${SLICER_BUILD_LOG}" || true; } | { grep -E '/CTK[-/]' || true; } | wc -l | tr -d ' ')
SLICER_CTK_WARNINGS=$({ grep ' warning:' "${SLICER_BUILD_LOG}" || true; } | { grep -E '/CTK[-/]' || true; } | wc -l | tr -d ' ')
SLICER_OWN_ERRORS=$((SLICER_ERRORS - SLICER_CTK_ERRORS))
SLICER_OWN_WARNINGS=$((SLICER_WARNINGS - SLICER_CTK_WARNINGS))

echo ""
echo "SLICER BUILD SUMMARY: exit_code=${SLICER_BUILD_EXIT} errors=${SLICER_ERRORS} (CTK-related: ${SLICER_CTK_ERRORS}, Slicer-own: ${SLICER_OWN_ERRORS}) warnings=${SLICER_WARNINGS} (CTK-related: ${SLICER_CTK_WARNINGS}, Slicer-own: ${SLICER_OWN_WARNINGS})"
echo "CTK build log:    ${CTK_BUILD_LOG}"
echo "Slicer build log: ${SLICER_BUILD_LOG}"

# Write machine-readable summary
cat > "${SLICER_BLD}/validate-slicer-build-summary.txt" <<EOSUMMARY
CTK_BRANCH=${CTK_BRANCH}
CTK_HASH=${CTK_HASH}
CTK_BUILD_EXIT=${CTK_BUILD_EXIT}
CTK_BUILD_ERRORS=${CTK_ERRORS}
CTK_BUILD_WARNINGS=${CTK_WARNINGS}
CTK_SRC_ERRORS=${CTK_SRC_ERRORS}
CTK_SRC_WARNINGS=${CTK_SRC_WARNINGS}
CTK_DEP_ERRORS=${CTK_DEP_ERRORS}
CTK_DEP_WARNINGS=${CTK_DEP_WARNINGS}
CTK_BUILD_LOG=${CTK_BUILD_LOG}
SLICER_BUILD_EXIT=${SLICER_BUILD_EXIT}
SLICER_BUILD_ERRORS=${SLICER_ERRORS}
SLICER_BUILD_WARNINGS=${SLICER_WARNINGS}
SLICER_CTK_ERRORS=${SLICER_CTK_ERRORS}
SLICER_CTK_WARNINGS=${SLICER_CTK_WARNINGS}
SLICER_OWN_ERRORS=${SLICER_OWN_ERRORS}
SLICER_OWN_WARNINGS=${SLICER_OWN_WARNINGS}
SLICER_BUILD_LOG=${SLICER_BUILD_LOG}
EOSUMMARY

if [ "${SLICER_BUILD_EXIT}" -ne 0 ] || [ "${SLICER_ERRORS}" -gt 0 ]; then
  echo "FAIL: Slicer build failed"
  echo "--- First errors ---"
  { grep ' error:' "${SLICER_BUILD_LOG}" || true; } | head -20
  exit 1
fi
