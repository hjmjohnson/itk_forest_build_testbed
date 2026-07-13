#!/usr/bin/env bash
# csv_scaffold.sh — Create the directory tree for a package in common_support_versions
#
# Usage:
#   csv_scaffold.sh <PKG> <GIT_TAG> [--repo <GIT_URL>] [--feature <SUFFIX>]
#
# Examples:
#   csv_scaffold.sh ITK v5.4.2 --repo https://github.com/InsightSoftwareConsortium/ITK.git
#   csv_scaffold.sh ITK v5.4.2 --feature shared
#   csv_scaffold.sh VTK v9.4.0 --repo https://github.com/Kitware/VTK.git

set -euo pipefail

CSV_ROOT="${CSV_ROOT:-${HOME}/src/common_support_versions}"

usage() {
    echo "Usage: $0 <PKG> <GIT_TAG> [--repo <GIT_URL>] [--feature <SUFFIX>]"
    echo ""
    echo "Arguments:"
    echo "  PKG       Package name (e.g., ITK, VTK, Eigen3)"
    echo "  GIT_TAG   Git tag to check out (e.g., v5.4.2)"
    echo ""
    echo "Options:"
    echo "  --repo <URL>       Git repository URL (required for first clone)"
    echo "  --feature <SUFFIX> Feature suffix for API-incompatible variants"
    echo ""
    echo "Environment:"
    echo "  CSV_ROOT   Override root directory (default: ~/src/common_support_versions)"
    exit 1
}

# --- Parse arguments ---
[[ $# -lt 2 ]] && usage

PKG="$1"; shift
GIT_TAG="$1"; shift

REPO_URL=""
FEATURE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo)    REPO_URL="$2"; shift 2 ;;
        --feature) FEATURE="$2"; shift 2 ;;
        --help|-h) usage ;;
        *)         echo "Unknown option: $1"; usage ;;
    esac
done

PKG_DIR="${CSV_ROOT}/${PKG}"
SRC_MAIN="${PKG_DIR}/src_main"
SRC_TAG="${PKG_DIR}/src_${GIT_TAG}"

if [[ -n "$FEATURE" ]]; then
    BLD_TAG="${PKG_DIR}/bld_${GIT_TAG}_${FEATURE}"
    INSTALL_TAG="${PKG_DIR}/installed_${GIT_TAG}_${FEATURE}"
else
    BLD_TAG="${PKG_DIR}/bld_${GIT_TAG}"
    INSTALL_TAG="${PKG_DIR}/installed_${GIT_TAG}"
fi

echo "=== Common Support Versions: Scaffolding ==="
echo "Package:   ${PKG}"
echo "Tag:       ${GIT_TAG}"
echo "Feature:   ${FEATURE:-<default>}"
echo "Root:      ${CSV_ROOT}"
echo ""

# --- Create package directory ---
mkdir -p "${PKG_DIR}"

# --- Clone primary source if it doesn't exist ---
if [[ ! -d "${SRC_MAIN}" ]]; then
    if [[ -z "$REPO_URL" ]]; then
        echo "ERROR: src_main does not exist and no --repo URL provided."
        echo "Please provide --repo <GIT_URL> for the initial clone."
        exit 1
    fi
    echo ">>> Cloning ${REPO_URL} into ${SRC_MAIN} ..."
    git clone "${REPO_URL}" "${SRC_MAIN}"
    echo "    Done."
else
    echo ">>> src_main already exists at ${SRC_MAIN}"
    # Fetch latest tags
    echo ">>> Fetching latest tags ..."
    git -C "${SRC_MAIN}" fetch --tags --prune 2>/dev/null || true
fi

# --- Create worktree for the tag ---
if [[ ! -d "${SRC_TAG}" ]]; then
    echo ">>> Creating worktree for ${GIT_TAG} at ${SRC_TAG} ..."
    git -C "${SRC_MAIN}" worktree add "${SRC_TAG}" "${GIT_TAG}"
    echo "    Done."
else
    echo ">>> Worktree already exists at ${SRC_TAG}"
fi

# --- Create build directory ---
if [[ ! -d "${BLD_TAG}" ]]; then
    echo ">>> Creating build directory ${BLD_TAG} ..."
    mkdir -p "${BLD_TAG}"
else
    echo ">>> Build directory already exists at ${BLD_TAG}"
fi

# --- Create install directory ---
if [[ ! -d "${INSTALL_TAG}" ]]; then
    echo ">>> Creating install directory ${INSTALL_TAG} ..."
    mkdir -p "${INSTALL_TAG}"
else
    echo ">>> Install directory already exists at ${INSTALL_TAG}"
fi

echo ""
echo "=== Scaffolding complete ==="
echo ""
echo "Next steps:"
echo "  1. Generate presets:  csv_gen_presets.py --pkg ${PKG} --tag ${GIT_TAG} ..."
echo "  2. Configure:         cmake --preset csv_${PKG}_${GIT_TAG}${FEATURE:+_${FEATURE}}"
echo "  3. Build:             cmake --build --preset csv_${PKG}_${GIT_TAG}${FEATURE:+_${FEATURE}}"
echo "  4. Install:           cmake --install ${BLD_TAG}"
