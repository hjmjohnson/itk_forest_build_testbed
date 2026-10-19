#!/usr/bin/env bash
# Map each test driver to the %m signature its raw profiles are named with,
# by running it once with no arguments into an empty directory.
# Usage: map_profile_signatures.sh <build-dir> <out-file>
set -euo pipefail
bld=$1
out=$2
scratch=$(mktemp -d)
: > "${out}"
for exe in "${bld}"/bin/*TestDriver; do
  [ -x "${exe}" ] || continue
  rm -f "${scratch}"/*.profraw
  args=()
  case "${exe}" in *GTestDriver) args=(--gtest_list_tests) ;; esac
  LLVM_PROFILE_FILE="${scratch}/%4m.profraw" timeout 120 "${exe}" ${args[@]+"${args[@]}"} < /dev/null > /dev/null 2>&1 || true
  sig=$(ls "${scratch}" | sed -n 's/_[0-9]*\.profraw$//p' | sort -u | head -1)
  printf '%s %s\n' "${sig:-NONE}" "$(basename "${exe}")" >> "${out}"
done
rm -rf "${scratch}"
