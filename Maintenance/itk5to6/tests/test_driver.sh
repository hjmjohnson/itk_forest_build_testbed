#!/usr/bin/env bash
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
DRV="$TOOLKIT/itk-migrate.sh"

# list shows a known task
out="$(bash "$DRV" list --level legacy-remove)"
assert_file_contains <(printf '%s' "$out") disallow-copy-and-move

# run a single task on a fixture repo
repo="$(mk_fixture_repo)"; cd "$repo"
printf 'ITK_DISALLOW_COPY_AND_ASSIGN(Foo);\n' > f.cxx; git add f.cxx >/dev/null
bash "$DRV" run disallow-copy-and-move "$repo" >/dev/null
assert_file_contains f.cxx ITK_DISALLOW_COPY_AND_MOVE

# status reports clean after the run
out="$(bash "$DRV" status "$repo")"
assert_file_contains <(printf '%s' "$out") clean

# status for glob-scoped task (cmake-lowercase) must be clean when only .cxx exists
repo2="$(mk_fixture_repo)"
printf 'MYMACRO(x);\n' > "$repo2/foo.cxx"
git -C "$repo2" add foo.cxx >/dev/null
out2="$(bash "$DRV" status "$repo2")"
grep -q 'cmake-lowercase.*clean' <(printf '%s' "$out2") || _fail "cmake-lowercase should be clean when no cmake files exist"

echo "PASS test_driver"
