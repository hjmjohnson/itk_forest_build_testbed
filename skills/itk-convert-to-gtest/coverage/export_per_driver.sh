#!/usr/bin/env bash
# Export line coverage separately for each test driver, using a profile
# merged only from that driver's own raw files, so that header templates
# compiled differently in different drivers never conflict.
# Executables other than test drivers (header tests, helper programs, test
# plugin libraries) are unchanged by the conversion and are not exported.
# Usage: export_per_driver.sh <build-dir> <out-dir>   (out-dir from run_coverage_tests.sh)
set -euo pipefail
bld=$1
out=$2
here=$(cd "$(dirname "$0")" && pwd)
xc=/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin

"${here}/map_profile_signatures.sh" "${bld}" "${out}/signatures.txt"
rm -rf "${out}/per_driver"
mkdir -p "${out}/per_driver"
: > "${out}/per_driver_warnings.txt"

while read -r sig driver; do
  raws=("${out}"/profraw/"${sig}"_*.profraw)
  [ -e "${raws[0]}" ] || { echo "${driver}: no profiles (not run)" >> "${out}/per_driver_warnings.txt"; continue; }
  "${xc}/llvm-profdata" merge -sparse "${raws[@]}" -o "${out}/per_driver/${driver}.profdata"
  "${xc}/llvm-cov" export -format=lcov -instr-profile "${out}/per_driver/${driver}.profdata" \
    "${bld}/bin/${driver}" \
    -ignore-filename-regex='(/test/|/ThirdParty/|/_deps/|-build/)' \
    > "${out}/per_driver/${driver}.lcov" 2> "${out}/per_driver/${driver}.err"
  if [ -s "${out}/per_driver/${driver}.err" ]; then
    printf '%s: %s\n' "${driver}" "$(tr '\n' ' ' < "${out}/per_driver/${driver}.err")" >> "${out}/per_driver_warnings.txt"
  fi
done < "${out}/signatures.txt"

ls "${out}"/per_driver/*.lcov | wc -l
wc -l < "${out}/per_driver_warnings.txt"
