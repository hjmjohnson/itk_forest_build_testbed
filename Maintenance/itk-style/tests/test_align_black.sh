#!/usr/bin/env bash
# Binary-independent tests for align-black.sh (do not require black 24.2.0).
# Exercise only the config-classification / add-config / hook paths.
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
ACB="$TOOLKIT/bin/align-black.sh"

# --- add-config (absent): creates [tool.black] and stages pyproject.toml ---
repo="$(mk_fixture_repo)"; cd "$repo"
bash "$ACB" add-config "$repo" >/dev/null
assert_file_contains "$repo/pyproject.toml" "[tool.black]"
assert_file_contains "$repo/pyproject.toml" "line-length = 88"
assert_file_contains "$repo/pyproject.toml" "py310"
assert_staged pyproject.toml

# --- add-config is idempotent when already ITKv6 (exit 0, no second section) ---
assert_exit_code 0 bash "$ACB" add-config "$repo"
n="$(grep -c '^\[tool\.black\]' "$repo/pyproject.toml")"
assert_eq 1 "$n" "exactly one [tool.black] section after idempotent re-run"

# --- different project style: REFUSE without --accept-restyle (exit 2, unchanged) ---
repo2="$(mk_fixture_repo)"; cd "$repo2"
cat > pyproject.toml <<'EOF'
[tool.black]
line-length = 120

[tool.other]
keep = true
EOF
git add pyproject.toml >/dev/null
rc=0; bash "$ACB" add-config "$repo2" >/dev/null 2>&1 || rc=$?
assert_eq 2 "$rc" "add-config refuses a different style without --accept-restyle"
assert_file_contains "$repo2/pyproject.toml" "line-length = 120"   # untouched

# --- with --accept-restyle: replace to ITKv6, preserve other sections ---
bash "$ACB" add-config --accept-restyle "$repo2" >/dev/null
assert_file_contains "$repo2/pyproject.toml" "line-length = 88"
assert_file_not_contains "$repo2/pyproject.toml" "line-length = 120"
assert_file_contains "$repo2/pyproject.toml" "[tool.other]"        # other sections kept
n="$(grep -c '^\[tool\.black\]' "$repo2/pyproject.toml")"
assert_eq 1 "$n" "exactly one [tool.black] section after restyle"

# --- hook prints the pinned ITKv6 black hook ---
out="$(bash "$ACB" hook "$repo2")"; printf '%s' "$out" > "$repo2/_hook.txt"
assert_file_contains "$repo2/_hook.txt" "psf/black"
assert_file_contains "$repo2/_hook.txt" "24.2.0"
assert_file_contains "$repo2/_hook.txt" "--target-version"

echo "PASS test_align_black"
