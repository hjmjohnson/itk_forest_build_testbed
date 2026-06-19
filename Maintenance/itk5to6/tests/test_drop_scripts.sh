#!/usr/bin/env bash
set -uo pipefail
source "$(dirname "$0")/helpers.sh"

repo="$(mk_fixture_repo)"
cd "$repo"

cat > a.cxx <<'EOF'
#if ITK_VERSION_MAJOR >= 6
new_api();
#else
old_api();
#endif
EOF

git add a.cxx >/dev/null
git commit -q -m "add fixture"

# default dry-run leaves file unchanged
bash "$TOOLKIT/drop/drop-itk-v5.sh" "$repo" >/dev/null 2>&1
assert_file_contains a.cxx old_api

# --apply removes the <v6 branch
bash "$TOOLKIT/drop/drop-itk-v5.sh" --apply "$repo" >/dev/null 2>&1
assert_file_contains a.cxx new_api
assert_file_not_contains a.cxx old_api
assert_staged a.cxx

# Test drop-itk-before-v5 discovers ITKV4_COMPATIBILITY and reports as ambiguous
repo="$(mk_fixture_repo)"; cd "$repo"
cat > v4.cxx <<'EOF'
#ifdef ITKV4_COMPATIBILITY
old_v4_path();
#endif
EOF
git add v4.cxx >/dev/null; git commit -q -m init
before="$(cat v4.cxx)"
rc=0; bash "$TOOLKIT/drop/drop-itk-before-v5.sh" --apply "$repo" >/dev/null 2>&1 || rc=$?
assert_eq 2 "$rc" "drop-before-v5 reports ITKV4_COMPATIBILITY as ambiguous"
assert_eq "$before" "$(cat v4.cxx)" "ITKV4_COMPATIBILITY file left intact"

echo "PASS test_drop_scripts"
