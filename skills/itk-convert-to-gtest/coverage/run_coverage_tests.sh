#!/usr/bin/env bash
# Run every test of the staging-run modules in a coverage build, then export
# line coverage for library sources (test sources, ThirdParty, and generated
# files excluded, since test files are renamed by the conversion).
# Usage: COVERAGE_MODULES_FILE=<modules.txt> run_coverage_tests.sh <build-dir> <out-dir> [ctest -j]
set -euo pipefail
bld=$1
out=$2
jobs=${3:-6}
xc=/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin

rm -rf "${out}"
mkdir -p "${out}/profraw"
labels="^($(paste -sd'|' "${COVERAGE_MODULES_FILE:?set COVERAGE_MODULES_FILE}"))\$"

LLVM_PROFILE_FILE="${out}/profraw/%4m.profraw" \
  ctest --test-dir "${bld}" -j"${jobs}" -L "${labels}" -E 'KWStyle' \
  --timeout 1800 --output-junit "${out}/ctest_junit.xml" > "${out}/ctest.log" 2>&1 || true

"${xc}/llvm-profdata" merge -sparse "${out}"/profraw/*.profraw -o "${out}/merged.profdata"

objects=()
for exe in "${bld}"/bin/*TestDriver; do
  [ -x "${exe}" ] && objects+=(-object "${exe}")
done

"${xc}/llvm-cov" export -format=lcov -instr-profile "${out}/merged.profdata" \
  "${objects[@]}" \
  -ignore-filename-regex='(/test/|/ThirdParty/|/_deps/|-build/)' > "${out}/coverage.lcov"

"${xc}/llvm-cov" report -instr-profile "${out}/merged.profdata" "${objects[@]}" \
  -ignore-filename-regex='(/test/|/ThirdParty/|/_deps/|-build/)' > "${out}/coverage_report.txt"

tail -3 "${out}/ctest.log"
tail -1 "${out}/coverage_report.txt"
