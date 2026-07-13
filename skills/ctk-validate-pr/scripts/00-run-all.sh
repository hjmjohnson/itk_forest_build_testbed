#!/usr/bin/env bash
# Full CTK validation pipeline: build, test, cache results, and generate report.
#
# Usage: 00-run-all.sh <ctk_src> <slicer_bld> <proposed_ref> <reference_ref> [<pr_number>]
#
#   ctk_src        CTK source directory (default: ~/src/CTK)
#   slicer_bld     Slicer superbuild directory (default: ~/src/Slicer-bld)
#   proposed_ref   Git ref to validate (branch, tag, hash, or "." for current HEAD)
#   reference_ref  Git ref for the baseline (e.g., 935c4e04 for Slicer stock CTK)
#                  Use "none" to skip comparative report and just validate proposed.
#   pr_number      Optional PR number to include in the report
#
# Results are cached by full commit hash in CACHE_DIR. If a cached result exists
# for a hash, the build/test steps are skipped and the cached summaries are reused.
# This allows reference baselines to be computed once and reused across runs.
#
# Exit code: 0 (always — failures are captured in the report, not fatal)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CTK_SRC="${1:-$HOME/src/CTK}"
SLICER_BLD="${2:-$HOME/src/Slicer-bld}"
PROPOSED_REF="${3:-.}"
REFERENCE_REF="${4:-none}"
PR_NUM="${5:-}"
DISPLAY_VAR="${DISPLAY:-:0}"
SUPERBLD5="${CTK_SRC}/cmake-build-clazy-qt5"
SUPERBLD6="${CTK_SRC}/cmake-build-clazy-qt6"
CACHE_DIR="${CTK_SRC}/.claude/validate-cache"

########################################################################
# Helper: resolve a git ref to a full hash
########################################################################
resolve_hash() {
  local ref="$1"
  local src="$2"
  if [ "${ref}" = "." ]; then
    (cd "${src}" && git rev-parse HEAD)
  else
    (cd "${src}" && git rev-parse "${ref}")
  fi
}

########################################################################
# Helper: check if cached results exist for a hash
########################################################################
cache_exists() {
  local hash="$1"
  [ -f "${CACHE_DIR}/${hash}/validate-complete" ]
}

########################################################################
# Helper: save current results to cache
########################################################################
save_to_cache() {
  local hash="$1"
  local dest="${CACHE_DIR}/${hash}"
  mkdir -p "${dest}"

  # CTK Qt5 results
  cp -f "${SUPERBLD5}/CTK-build/validate-build.log" "${dest}/ctk-qt5-build.log" 2>/dev/null || true
  cp -f "${SUPERBLD5}/CTK-build/validate-test-summary-qt5.txt" "${dest}/ctk-qt5-test-summary.txt" 2>/dev/null || true

  # CTK Qt6 results
  cp -f "${SUPERBLD6}/CTK-build/validate-build.log" "${dest}/ctk-qt6-build.log" 2>/dev/null || true
  cp -f "${SUPERBLD6}/CTK-build/validate-test-summary-qt6.txt" "${dest}/ctk-qt6-test-summary.txt" 2>/dev/null || true

  # Slicer results
  cp -f "${SLICER_BLD}/validate-slicer-build-summary.txt" "${dest}/slicer-build-summary.txt" 2>/dev/null || true
  cp -f "${SLICER_BLD}/validate-slicer-test-summary.txt" "${dest}/slicer-test-summary.txt" 2>/dev/null || true
  cp -f "${SLICER_BLD}/validate-slicer-ctk-build.log" "${dest}/slicer-ctk-build.log" 2>/dev/null || true
  cp -f "${SLICER_BLD}/validate-slicer-build.log" "${dest}/slicer-build.log" 2>/dev/null || true

  # Record metadata
  (cd "${CTK_SRC}" && git log --oneline -1 HEAD) > "${dest}/commit-info.txt" 2>/dev/null || true
  date -u +%Y-%m-%dT%H:%M:%SZ > "${dest}/timestamp.txt"
  uname -srm > "${dest}/platform.txt"

  # Mark as complete
  touch "${dest}/validate-complete"
  echo "Results cached: ${dest}"
}

########################################################################
# Helper: restore cached results into the working locations
########################################################################
restore_from_cache() {
  local hash="$1"
  local src="${CACHE_DIR}/${hash}"

  cp -f "${src}/ctk-qt5-build.log" "${SUPERBLD5}/CTK-build/validate-build.log" 2>/dev/null || true
  cp -f "${src}/ctk-qt5-test-summary.txt" "${SUPERBLD5}/CTK-build/validate-test-summary-qt5.txt" 2>/dev/null || true
  cp -f "${src}/ctk-qt6-build.log" "${SUPERBLD6}/CTK-build/validate-build.log" 2>/dev/null || true
  cp -f "${src}/ctk-qt6-test-summary.txt" "${SUPERBLD6}/CTK-build/validate-test-summary-qt6.txt" 2>/dev/null || true
  cp -f "${src}/slicer-build-summary.txt" "${SLICER_BLD}/validate-slicer-build-summary.txt" 2>/dev/null || true
  cp -f "${src}/slicer-test-summary.txt" "${SLICER_BLD}/validate-slicer-test-summary.txt" 2>/dev/null || true
  cp -f "${src}/slicer-ctk-build.log" "${SLICER_BLD}/validate-slicer-ctk-build.log" 2>/dev/null || true
  cp -f "${src}/slicer-build.log" "${SLICER_BLD}/validate-slicer-build.log" 2>/dev/null || true
}

########################################################################
# Helper: run full build+test pipeline for current HEAD
########################################################################
run_validation() {
  local label="$1"
  QT5_BUILD_OK=false
  QT6_BUILD_OK=false
  SLICER_BUILD_OK=false

  echo "======== ${label}: Build CTK Qt5 ========"
  if [ -d "${SUPERBLD5}/CTK-build" ]; then
    bash "${SCRIPT_DIR}/01-build-ctk.sh" 5 "${CTK_SRC}" 2>&1
    if [ $? -ne 0 ]; then
      echo "Inner build failed — retrying via superbuild target..."
      cmake --build "${SUPERBLD5}" --target CTK -j"$(nproc 2>/dev/null || echo 8)" 2>&1 | \
        tee "${SUPERBLD5}/CTK-build/validate-build.log"
      [ ${PIPESTATUS[0]} -eq 0 ] && QT5_BUILD_OK=true || echo "FAIL: CTK Qt5 build failed."
    else
      QT5_BUILD_OK=true
    fi
  else
    echo "SKIP: Qt5 build directory not found"
  fi
  echo ""

  echo "======== ${label}: Build CTK Qt6 ========"
  if [ -d "${SUPERBLD6}/CTK-build" ]; then
    bash "${SCRIPT_DIR}/01-build-ctk.sh" 6 "${CTK_SRC}" 2>&1
    if [ $? -ne 0 ]; then
      echo "Inner build failed — retrying via superbuild target..."
      cmake --build "${SUPERBLD6}" --target CTK -j"$(nproc 2>/dev/null || echo 8)" 2>&1 | \
        tee "${SUPERBLD6}/CTK-build/validate-build.log"
      [ ${PIPESTATUS[0]} -eq 0 ] && QT6_BUILD_OK=true || echo "FAIL: CTK Qt6 build failed."
    else
      QT6_BUILD_OK=true
    fi
  else
    echo "SKIP: Qt6 build directory not found"
  fi
  echo ""

  if [ "${QT5_BUILD_OK}" = true ]; then
    echo "======== ${label}: Test CTK Qt5 ========"
    DISPLAY="${DISPLAY_VAR}" bash "${SCRIPT_DIR}/02-test-ctk.sh" 5 "${CTK_SRC}" "${DISPLAY_VAR}" 2>&1
    echo ""
  else
    echo "======== ${label}: SKIP CTK Qt5 tests (build failed) ========"
    echo ""
  fi

  if [ "${QT6_BUILD_OK}" = true ]; then
    echo "======== ${label}: Test CTK Qt6 ========"
    DISPLAY="${DISPLAY_VAR}" bash "${SCRIPT_DIR}/02-test-ctk.sh" 6 "${CTK_SRC}" "${DISPLAY_VAR}" 2>&1
    echo ""
  else
    echo "======== ${label}: SKIP CTK Qt6 tests (build failed) ========"
    echo ""
  fi

  if [ -d "${SLICER_BLD}" ]; then
    echo "======== ${label}: Build Slicer ========"
    bash "${SCRIPT_DIR}/03-build-slicer.sh" "${CTK_SRC}" "${SLICER_BLD}" 2>&1
    [ $? -eq 0 ] && SLICER_BUILD_OK=true || echo "FAIL: Slicer build failed."
    echo ""
  else
    echo "======== ${label}: SKIP Slicer (not found) ========"
    echo ""
  fi

  if [ "${SLICER_BUILD_OK}" = true ]; then
    echo "======== ${label}: Test Slicer ========"
    DISPLAY="${DISPLAY_VAR}" bash "${SCRIPT_DIR}/04-test-slicer.sh" "${SLICER_BLD}" "${DISPLAY_VAR}" 2>&1
    echo ""
  else
    echo "======== ${label}: SKIP Slicer tests ========"
    echo ""
  fi
}

########################################################################
# Step 0: Git checkout management
########################################################################
ORIGINAL_BRANCH=""
DID_STASH=false
DID_CHECKOUT=false

need_checkout() {
  local ref="$1"
  [ "${ref}" != "." ]
}

do_checkout() {
  local ref="$1"
  cd "${CTK_SRC}"
  if [ -z "${ORIGINAL_BRANCH}" ]; then
    ORIGINAL_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
    [ "${ORIGINAL_BRANCH}" = "HEAD" ] && ORIGINAL_BRANCH=$(git rev-parse --short HEAD)
  fi

  if [ "${DID_STASH}" = false ]; then
    if ! git diff --quiet HEAD 2>/dev/null || ! git diff --cached --quiet HEAD 2>/dev/null || \
       [ "$(git ls-files --others --exclude-standard | head -1)" != "" ]; then
      echo "Stashing uncommitted changes..."
      git stash --include-untracked -m "ctk-validate-pr-auto-stash" 2>&1
      DID_STASH=true
    fi
  fi

  echo "Checking out ${ref}..."
  if git show-ref --verify --quiet "refs/heads/${ref}" 2>/dev/null; then
    git checkout "${ref}" 2>&1
  elif git show-ref --verify --quiet "refs/remotes/${ref}" 2>/dev/null; then
    git checkout --detach "${ref}" 2>&1
  else
    git checkout --detach "${ref}" 2>&1
  fi
  DID_CHECKOUT=true
}

cleanup_git() {
  if [ "${DID_CHECKOUT}" = true ] && [ -n "${ORIGINAL_BRANCH}" ]; then
    cd "${CTK_SRC}"
    echo ""
    echo "Restoring original branch (${ORIGINAL_BRANCH})..."
    if echo "${ORIGINAL_BRANCH}" | grep -qE '^[0-9a-f]+$'; then
      git checkout --detach "${ORIGINAL_BRANCH}" 2>&1
    else
      git checkout "${ORIGINAL_BRANCH}" 2>&1
    fi
    if [ "${DID_STASH}" = true ]; then
      echo "Popping stash..."
      git stash pop 2>&1 || echo "WARNING: git stash pop failed — check 'git stash list'"
    fi
  fi
}
trap cleanup_git EXIT

########################################################################
# Resolve hashes — fetch latest for branches, tags, and PRs
########################################################################
mkdir -p "${CACHE_DIR}"

# Resolve a ref to a full hash, fetching from upstream if needed.
# Handles: ".", local branches, remote branches (upstream/master),
# PR numbers (pr/1409 or just 1409), tags, and raw hashes.
resolve_ref() {
  local ref="$1"
  local src="$2"
  cd "${src}"

  # Current HEAD
  if [ "${ref}" = "." ]; then
    git rev-parse HEAD
    return
  fi

  # PR number pattern: "pr/NNN" or bare number
  local pr_num=""
  if echo "${ref}" | grep -qE '^pr/[0-9]+$'; then
    pr_num="${ref#pr/}"
  elif echo "${ref}" | grep -qE '^[0-9]{1,6}$'; then
    # Could be a PR number — try fetching it; fall through to hash if it fails
    pr_num="${ref}"
  fi

  if [ -n "${pr_num}" ]; then
    echo "Fetching PR #${pr_num} from upstream..." >&2
    if git fetch upstream "pull/${pr_num}/head" >/dev/null 2>&1; then
      git rev-parse FETCH_HEAD
      return
    fi
    # If fetch failed and ref is numeric, it might be a short hash — fall through
  fi

  # Remote branch: fetch to ensure we have the latest
  if echo "${ref}" | grep -qE '/'; then
    local remote="${ref%%/*}"
    local branch="${ref#*/}"
    echo "Fetching ${branch} from ${remote}..." >&2
    git fetch "${remote}" "${branch}" >/dev/null 2>&1 || true
  else
    # Local branch or tag — fetch upstream in case it's a remote tracking branch
    git fetch upstream "${ref}" >/dev/null 2>&1 || true
  fi

  # Try resolving locally (works for local branches, tags, remote refs, hashes)
  local hash
  hash=$(git rev-parse "${ref}" 2>/dev/null || echo "")
  if [ -n "${hash}" ]; then
    echo "${hash}"
    return
  fi

  echo "ERROR: Cannot resolve ref '${ref}'" >&2
  echo ""
}

PROPOSED_HASH=$(resolve_ref "${PROPOSED_REF}" "${CTK_SRC}")
if [ -z "${PROPOSED_HASH}" ]; then
  exit 0
fi
PROPOSED_SHORT="${PROPOSED_HASH:0:8}"

REFERENCE_HASH=""
REFERENCE_SHORT=""
if [ "${REFERENCE_REF}" != "none" ]; then
  REFERENCE_HASH=$(resolve_ref "${REFERENCE_REF}" "${CTK_SRC}")
  if [ -z "${REFERENCE_HASH}" ]; then
    exit 0
  fi
  REFERENCE_SHORT="${REFERENCE_HASH:0:8}"
fi

echo "========================================================"
echo " CTK Validation Pipeline"
echo "========================================================"
echo "CTK source:    ${CTK_SRC}"
echo "Proposed:      ${PROPOSED_REF} (${PROPOSED_SHORT})"
[ -n "${REFERENCE_HASH}" ] && echo "Reference:     ${REFERENCE_REF} (${REFERENCE_SHORT})"
echo "Slicer build:  ${SLICER_BLD}"
echo "PR:            ${PR_NUM:-none}"
echo "Cache:         ${CACHE_DIR}"
echo "Started:       $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "========================================================"
echo ""

########################################################################
# Validate REFERENCE (if requested and not cached)
########################################################################
if [ -n "${REFERENCE_HASH}" ]; then
  if cache_exists "${REFERENCE_HASH}"; then
    echo "======== Reference ${REFERENCE_SHORT}: CACHED — reusing previous results ========"
    echo "Cache: ${CACHE_DIR}/${REFERENCE_HASH}"
    echo ""
  else
    echo "======== Validating REFERENCE: ${REFERENCE_REF} (${REFERENCE_SHORT}) ========"
    do_checkout "${REFERENCE_HASH}"
    echo ""
    run_validation "Reference"
    save_to_cache "${REFERENCE_HASH}"
    echo ""
  fi
fi

########################################################################
# Validate PROPOSED (if not cached)
########################################################################
if cache_exists "${PROPOSED_HASH}"; then
  echo "======== Proposed ${PROPOSED_SHORT}: CACHED — reusing previous results ========"
  echo "Cache: ${CACHE_DIR}/${PROPOSED_HASH}"
  echo ""
else
  echo "======== Validating PROPOSED: ${PROPOSED_REF} (${PROPOSED_SHORT}) ========"
  if need_checkout "${PROPOSED_REF}"; then
    do_checkout "${PROPOSED_HASH}"
  fi
  echo ""
  run_validation "Proposed"
  save_to_cache "${PROPOSED_HASH}"
  echo ""
fi

########################################################################
# Restore cached results for report generation
# (report reads from the standard working locations)
########################################################################
restore_from_cache "${PROPOSED_HASH}"

########################################################################
# Generate report
########################################################################
echo "======== Generate Report ========"
echo ""
REFERENCE_ARG=""
[ -n "${REFERENCE_HASH}" ] && REFERENCE_ARG="${REFERENCE_HASH}"
bash "${SCRIPT_DIR}/05-generate-report.sh" \
  "${CTK_SRC}" "${SLICER_BLD}" "${PROPOSED_HASH}" "${REFERENCE_ARG}" "${PR_NUM}" 2>&1

echo ""
echo "========================================================"
echo " Validation complete: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "========================================================"
