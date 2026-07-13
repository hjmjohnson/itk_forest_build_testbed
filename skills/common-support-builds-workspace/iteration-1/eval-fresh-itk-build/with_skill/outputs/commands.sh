#!/usr/bin/env bash
# Build ITK v5.4.2 as a shared library for USE_SYSTEM_ITK with BRAINSTools
# All configuration is done via CMakeUserPresets.json -- no -D flags on the command line.

set -euo pipefail

PKG="ITK"
GIT_TAG="v5.4.2"
FEATURE="shared"
CSV_ROOT="${HOME}/src/common_support_versions"
PKG_ROOT="${CSV_ROOT}/${PKG}"
SRC_MAIN="${PKG_ROOT}/src_main"
SRC_TAG="${PKG_ROOT}/src_${GIT_TAG}"
BLD_TAG="${PKG_ROOT}/bld_${GIT_TAG}_${FEATURE}"
INSTALL_TAG="${PKG_ROOT}/installed_${GIT_TAG}_${FEATURE}"
ITK_REPO="https://github.com/InsightSoftwareConsortium/ITK.git"

# Determine parallel job count (macOS vs Linux)
if command -v sysctl &>/dev/null; then
  JOBS=$(sysctl -n hw.logicalcpu)
else
  JOBS=$(nproc)
fi

# Step 1: Scaffold the directory tree
mkdir -p "${PKG_ROOT}"

if [ ! -d "${SRC_MAIN}/.git" ]; then
  git clone "${ITK_REPO}" "${SRC_MAIN}"
fi

git -C "${SRC_MAIN}" fetch --tags

if [ ! -d "${SRC_TAG}" ]; then
  git -C "${SRC_MAIN}" worktree add "${SRC_TAG}" "${GIT_TAG}"
fi

mkdir -p "${BLD_TAG}"
mkdir -p "${INSTALL_TAG}"

# Step 2: Generate CMakeUserPresets.json in the source worktree
cp itk_presets.json "${SRC_TAG}/CMakeUserPresets.json"

# Step 3: Configure using the preset (no -D flags)
cmake --preset csv_ITK_v5.4.2_shared --source-dir "${SRC_TAG}"

# Step 4: Build
cmake --build --preset csv_ITK_v5.4.2_shared -j"${JOBS}"

# Step 5: Install
cmake --install "${BLD_TAG}"

# Step 6: Verify
if [ -f "${INSTALL_TAG}/lib/cmake/ITK-5.4/ITKConfig.cmake" ]; then
  echo "OK: ITKConfig.cmake found at ${INSTALL_TAG}/lib/cmake/ITK-5.4/"
else
  echo "WARNING: ITKConfig.cmake not found"
fi
