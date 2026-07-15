#!/usr/bin/env bash
# Tests for itk-cleanup-pr-lifecycle helper scripts.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill_dir="$(dirname "$here")"
fail=0
check() { # check <description> <condition-exit-code>
  if [ "$2" -eq 0 ]; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi
}

# --- list-cleanup-patterns.sh ---
out="$(bash "$skill_dir/list-cleanup-patterns.sh")"; rc=$?
check "list-cleanup-patterns.sh exits 0"                 "$([ $rc -eq 0 ] && echo 0 || echo 1)"
grep -qx "itk-container-size-to-empty" <<<"$out"; check "lists itk-container-size-to-empty" $?
grep -qx "itk-emplace-back-construct"  <<<"$out"; check "lists itk-emplace-back-construct"  $?
if grep -qx "itk-start-worktree" <<<"$out"; then check "excludes itk-start-worktree (no detect.sh)" 1; else check "excludes itk-start-worktree (no detect.sh)" 0; fi
if grep -qx "itk-cleanup-pr-lifecycle" <<<"$out"; then check "excludes self" 1; else check "excludes self" 0; fi

echo "----"
[ "$fail" -eq 0 ] && echo "ALL PASS" || { echo "SOME FAILED"; exit 1; }
