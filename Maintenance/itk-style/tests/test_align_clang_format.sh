#!/usr/bin/env bash
# Binary-independent tests: do not require a clang-format install. They exercise
# add-config, hook, and the missing-config check path (which does not need clang-format).
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
ACF="$TOOLKIT/bin/align-clang-format.sh"

# --- add-config writes the ITKv6 .clang-format and stages it ---
repo="$(mk_fixture_repo)"; cd "$repo"
bash "$ACF" add-config "$repo" >/dev/null
assert_file_contains "$repo/.clang-format" "19.1.7"
assert_staged .clang-format

# --- add-config is idempotent (already-canonical => nothing to do, exit 0) ---
assert_exit_code 0 bash "$ACF" add-config "$repo"

# --- check reports config present once added; missing config exits 2 ---
repo2="$(mk_fixture_repo)"; cd "$repo2"
printf 'int main(){return 0;}\n' > a.cxx; git add a.cxx >/dev/null
# no .clang-format yet -> check must flag (exit 2), and must NOT crash without clang-format
rc=0; bash "$ACF" check "$repo2" >/dev/null 2>&1 || rc=$?
assert_eq 2 "$rc" "check flags missing config / drift with exit 2"

# --- hook prints the pinned ITKv6 clang-format hook snippet ---
out="$(bash "$ACF" hook "$repo2")"
printf '%s' "$out" > "$repo2/_hook.txt"
assert_file_contains "$repo2/_hook.txt" "mirrors-clang-format"
assert_file_contains "$repo2/_hook.txt" "v19.1.7"
assert_file_contains "$repo2/_hook.txt" "--style=file"

# --- the vendored canonical config carries the exact version marker ---
assert_file_contains "$TOOLKIT/assets/itkv6.clang-format" "19.1.7"

# --- outdated ITK .clang-format: add-config UPDATES it to 19.1.7 (exit 0) ---
repo3="$(mk_fixture_repo)"; cd "$repo3"
cat > .clang-format <<'EOF'
## This config file is only relevant for clang-format version 14.0.0
## Use the script Utilities/Maintenance/clang-format.bash to maintain style.
BasedOnStyle: LLVM
EOF
git add .clang-format >/dev/null
assert_exit_code 0 bash "$ACF" add-config "$repo3"
assert_file_contains "$repo3/.clang-format" "19.1.7"
assert_file_not_contains "$repo3/.clang-format" "14.0.0"

# --- different (non-ITK) .clang-format: REFUSE without --accept-restyle (exit 2, unchanged) ---
repo4="$(mk_fixture_repo)"; cd "$repo4"
printf 'BasedOnStyle: Google\nColumnLimit: 100\n' > .clang-format
git add .clang-format >/dev/null
rc=0; bash "$ACF" add-config "$repo4" >/dev/null 2>&1 || rc=$?
assert_eq 2 "$rc" "add-config refuses a non-ITK style without --accept-restyle"
assert_file_contains "$repo4/.clang-format" "Google"   # untouched

# --- with --accept-restyle: replace the project style with ITKv6 ---
bash "$ACF" add-config --accept-restyle "$repo4" >/dev/null
assert_file_contains "$repo4/.clang-format" "19.1.7"
assert_file_not_contains "$repo4/.clang-format" "Google"

# --- doctor never crashes (returns 0 if a runner exists, non-zero otherwise) ---
rc=0; bash "$ACF" doctor "$repo2" >/dev/null 2>&1 || rc=$?
case "$rc" in 0|1) : ;; *) _fail "doctor returned unexpected code $rc" ;; esac

echo "PASS test_align_clang_format"
