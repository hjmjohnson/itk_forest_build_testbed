#!/usr/bin/env bash
# Build ITK v5.4.2 with AddressSanitizer (ASAN) variant
# Assumes src_main, src_v5.4.2, bld_v5.4.2, and installed_v5.4.2 already exist.
# Using default Apple Clang compiler (no compiler suffix needed -- only _asan suffix).

set -euo pipefail

CSV_ROOT="$HOME/src/common_support_versions/ITK"

# 1. Scaffold the ASAN variant directories
scripts/csv_scaffold.sh ITK v5.4.2 --feature asan

# 2. Generate / update CMakeUserPresets.json in the source worktree
python3 scripts/csv_gen_presets.py \
  --pkg ITK \
  --tag v5.4.2 \
  --feature asan \
  --source-dir  "${CSV_ROOT}/src_v5.4.2" \
  --build-dir   "${CSV_ROOT}/bld_v5.4.2_asan" \
  --install-dir "${CSV_ROOT}/installed_v5.4.2_asan" \
  --cache-var "CMAKE_CXX_FLAGS:STRING=-mtune=native -march=native -fsanitize=address -fno-omit-frame-pointer -fno-optimize-sibling-calls" \
  --cache-var "CMAKE_C_FLAGS:STRING=-mtune=native -march=native -fsanitize=address -fno-omit-frame-pointer -fno-optimize-sibling-calls" \
  --cache-var "CMAKE_EXE_LINKER_FLAGS:STRING=-fsanitize=address" \
  --cache-var "CMAKE_SHARED_LINKER_FLAGS:STRING=-fsanitize=address" \
  --cache-var "CMAKE_MODULE_LINKER_FLAGS:STRING=-fsanitize=address" \
  --cache-var "ITK_LEGACY_REMOVE:BOOL=ON" \
  --cache-var "ITK_BUILD_DEFAULT_MODULES:BOOL=ON"

# 3. Configure
cmake --preset csv_ITK_v5.4.2_asan

# 4. Build
cmake --build --preset csv_ITK_v5.4.2_asan -j$(sysctl -n hw.logicalcpu)

# 5. Install
cmake --install "${CSV_ROOT}/bld_v5.4.2_asan"
