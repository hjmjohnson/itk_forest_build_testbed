#!/usr/bin/env bash
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
fail=0; pass=0
for t in "$here"/test_*.sh; do
  if bash "$t"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAILED: $t"; fi
done
printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
