#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/helpers.sh"

repo="$(mk_fixture_repo)"
cd "$repo"
printf 'hello\n' > a.txt
git add a.txt
assert_staged a.txt
assert_file_contains a.txt hello
assert_file_not_contains a.txt goodbye
assert_exit_code 0 true
assert_exit_code 1 false
echo "PASS test_harness_selftest"
