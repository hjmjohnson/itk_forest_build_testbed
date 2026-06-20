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

# base-branch report: warn when the checkout is behind origin's primary branch
repo3="$(mk_fixture_repo)"; cd "$repo3"
printf 'a\n' > x; git add x >/dev/null; git commit -qm A
br="$(git symbolic-ref --short HEAD)"
printf 'b\n' >> x; git add x >/dev/null; git commit -qm B
git update-ref refs/remotes/origin/main HEAD                       # origin/main = B
git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
git -c advice.detachedHead=false checkout -q HEAD~1               # HEAD = A (1 behind)
out="$(bash "$DRV" status --no-fetch "$repo3" 2>&1)"             # --no-fetch: offline fixture, no real remote
grep -q "BASE WARNING" <(printf '%s' "$out") || _fail "base check must warn when behind origin primary branch"
out="$(MC_NO_BASE_CHECK=1 bash "$DRV" status "$repo3" 2>&1)"
if grep -q "BASE WARNING" <(printf '%s' "$out"); then _fail "MC_NO_BASE_CHECK=1 must suppress base warning"; fi
git checkout -q "$br"                                            # back to B == origin/main
out="$(bash "$DRV" status --no-fetch "$repo3" 2>&1)"
grep -qE "base: HEAD .* == origin/main" <(printf '%s' "$out") || _fail "base check must confirm when at origin primary branch"

# level stops after the first task that stages changes (one clean commit per task)
repo4="$(mk_fixture_repo)"; cd "$repo4"
printf 'int n = atoi(s);\n' > a.cxx
printf 'IF(A)\nENDIF(A)\n' > CMakeLists.txt
git add a.cxx CMakeLists.txt >/dev/null; git commit -qm base
bash "$DRV" level prep-v5 --no-fetch "$repo4" >/dev/null 2>&1; rc=$?
[ "$rc" -eq 3 ] || _fail "level must stop with 3 after the first staging task, got $rc"
assert_staged a.cxx                                              # atoi-atof ran and staged
if git -C "$repo4" diff --cached --name-only | grep -qx CMakeLists.txt; then
  _fail "cmake-lowercase must not run after a prior task staged changes"
fi

# review: preview each pending task; Y applies + Y commits one clean commit
repo5="$(mk_fixture_repo)"; cd "$repo5"
printf 'int n = atoi(s);\n' > a.cxx
git add a.cxx >/dev/null; git commit -qm base
before="$(git rev-list --count HEAD)"
printf 'y\ny\n' | bash "$DRV" review --level prep-v5 --no-fetch "$repo5" >/dev/null 2>&1
after="$(git rev-list --count HEAD)"
assert_file_contains a.cxx "std::stoi(s)"
[ "$after" -eq "$((before + 1))" ] || _fail "review (Y/Y) should create exactly one commit (before=$before after=$after)"
# review with 'n' (decline) applies nothing and creates no commit
repo6="$(mk_fixture_repo)"; cd "$repo6"
printf 'int n = atoi(s);\n' > b.cxx; git add b.cxx >/dev/null; git commit -qm base
before="$(git rev-list --count HEAD)"
printf 'n\n' | bash "$DRV" review --level prep-v5 --no-fetch "$repo6" >/dev/null 2>&1
assert_file_contains b.cxx "atoi(s)"
[ "$(git rev-list --count HEAD)" -eq "$before" ] || _fail "review with 'n' must not commit"

echo "PASS test_driver"
