#!/usr/bin/env bash
# Configure an LLVM source-based coverage build of ITK with every module
# touched by the GoogleTest staging run enabled.
# Usage: COVERAGE_MODULES_FILE=<modules.txt> configure_coverage_build.sh <source-dir> <build-dir>
# modules.txt: one ITK module name per line. Optional ITK_DATA_STORE: ExternalData object store.
set -euo pipefail
src=$1
bld=$2
xc=/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin
cov="-fprofile-instr-generate -fcoverage-mapping"

module_flags=()
while IFS= read -r m; do
  module_flags+=("-DModule_${m}=ON")
done < "${COVERAGE_MODULES_FILE:?set COVERAGE_MODULES_FILE to a file of module names}"

cmake -G Ninja -S "${src}" -B "${bld}" \
  -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_C_FLAGS_DEBUG="-O0" -DCMAKE_CXX_FLAGS_DEBUG="-O0" \
  -DCMAKE_C_FLAGS="${cov}" -DCMAKE_CXX_FLAGS="${cov}" \
  -DCMAKE_EXE_LINKER_FLAGS="-fprofile-instr-generate" \
  -DCMAKE_SHARED_LINKER_FLAGS="-fprofile-instr-generate" \
  -DCMAKE_C_COMPILER="${xc}/cc" -DCMAKE_CXX_COMPILER="${xc}/c++" \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=15.0 \
  -DBUILD_SHARED_LIBS=OFF -DBUILD_TESTING=ON -DBUILD_EXAMPLES=OFF \
  -DITK_BUILD_DEFAULT_MODULES=OFF -DModule_ITKGoogleTest=ON \
  ${ITK_DATA_STORE:+-DExternalData_OBJECT_STORES=${ITK_DATA_STORE}} \
  "${module_flags[@]}"
