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
grep -qx "itk-mechanical-cleanup:container-size-to-empty" <<<"$out"; check "lists container-size-to-empty pattern" $?
grep -qx "itk-mechanical-cleanup:emplace-back-construct"  <<<"$out"; check "lists emplace-back-construct pattern"  $?
grep -qx "itk-declare-then-init"                          <<<"$out"; check "lists the script-based payload"        $?
# Every mechanical-cleanup payload is qualified; a bare pattern name is a bug.
if grep -qx "container-size-to-empty" <<<"$out"; then check "payload names are qualified" 1; else check "payload names are qualified" 0; fi
if grep -qx "itk-start-worktree" <<<"$out"; then check "excludes itk-start-worktree (not a payload)" 1; else check "excludes itk-start-worktree (not a payload)" 0; fi
if grep -qx "itk-cleanup-pr-lifecycle" <<<"$out"; then check "excludes self" 1; else check "excludes self" 0; fi

# --- validate-lifecycle-refs.sh ---
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
# A fixture that cites a real rule and a bogus one:
cat >"$tmp/GOOD.md" <<'EOF'
Uses skills/itk-start-worktree and obeys rules/pre-commit-mandatory.md.
EOF
cat >"$tmp/BAD.md" <<'EOF'
Obeys rules/this-rule-does-not-exist.md.
EOF
bash "$skill_dir/validate-lifecycle-refs.sh" "$tmp/GOOD.md"; check "validator PASSES a good fixture" $?
if bash "$skill_dir/validate-lifecycle-refs.sh" "$tmp/BAD.md" >/dev/null 2>&1; then
  check "validator FAILS a bogus-rule fixture" 1
else
  check "validator FAILS a bogus-rule fixture" 0
fi

echo "----"
[ "$fail" -eq 0 ] && echo "ALL PASS" || { echo "SOME FAILED"; exit 1; }
