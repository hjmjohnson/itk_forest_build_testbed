#!/usr/bin/env bash
# TDD test for manual/ scripts — written BEFORE implementation (RED phase).
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
M="$TOOLKIT/manual"

# --- multithreader-backends: safe renames ---
repo="$(mk_fixture_repo)"; cd "$repo"
cat > a.cxx << 'EOF'
filter->SetNumberOfThreads(4);
auto s = ThreadInfoStruct{};
filter->GetNumberOfThreads();
EOF
git add a.cxx >/dev/null
bash "$M/multithreader-backends.sh" "$repo" >/dev/null || true
assert_file_contains a.cxx "SetNumberOfWorkUnits"
assert_file_contains a.cxx "WorkUnitInfo"
assert_file_contains a.cxx "GetNumberOfWorkUnits"
assert_file_not_contains a.cxx "SetNumberOfThreads"
assert_file_not_contains a.cxx "ThreadInfoStruct"

# --- spatialobject-space: safe renames, IsInside must NOT be touched ---
repo2="$(mk_fixture_repo)"; cd "$repo2"
cat > b.cxx << 'EOF'
so->AddSpatialObject(c);
so->GetObjects();
so->RemoveSpatialObject(c);
if (so->IsInside(pt)) {}
EOF
git add b.cxx >/dev/null
bash "$M/spatialobject-space.sh" "$repo2" >/dev/null || true
assert_file_contains b.cxx "AddChild"
assert_file_contains b.cxx "GetObjects"      # must NOT be auto-renamed (too generic)
assert_file_not_contains b.cxx "GetChildren" # confirm GetObjects was not touched
assert_file_contains b.cxx "RemoveChild"
assert_file_contains b.cxx "IsInside"        # must NOT be renamed

# --- barrier-to-parallelize: report-only, exit 2 on hit, exit 0 on clean ---
repo3="$(mk_fixture_repo)"; cd "$repo3"
cat > c.cxx << 'EOF'
itk::Barrier b;
b.Initialize(4);
EOF
git add c.cxx >/dev/null
rc=0
bash "$M/barrier-to-parallelize.sh" "$repo3" >/dev/null 2>&1 || rc=$?
assert_eq 2 "$rc" "barrier-to-parallelize should exit 2 on hit"

repo4="$(mk_fixture_repo)"; cd "$repo4"
printf '// no barriers here\n' > clean.cxx
git add clean.cxx >/dev/null
rc2=0
bash "$M/barrier-to-parallelize.sh" "$repo4" >/dev/null 2>&1 || rc2=$?
assert_eq 0 "$rc2" "barrier-to-parallelize should exit 0 on clean repo"

echo "PASS test_manual"
