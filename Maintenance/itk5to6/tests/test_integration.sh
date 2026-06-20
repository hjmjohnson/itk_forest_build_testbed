#!/usr/bin/env bash
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
DRV="$TOOLKIT/itk-migrate.sh"
repo="$(mk_fixture_repo)"; cd "$repo"
cat > big.cxx <<'EOF'
auto p = ITK_NULLPTR;
itkTypeMacro(Foo, Super);
ITK_DISALLOW_COPY_AND_ASSIGN(Foo);
using C = CoordRepType;
void V() ITKv5_CONST;
#if ITK_VERSION_MAJOR >= 6
new_api();
#else
old_api();
#endif
EOF
git add big.cxx >/dev/null; git commit -q -m init
# This test verifies end-to-end transform correctness across the whole pipeline,
# not the one-commit-per-task discipline (covered by test_driver/test_prep_v5),
# so it intentionally chains tasks without committing between them.
export MC_ALLOW_DIRTY=1
for lvl in prep-v5 mandatory legacy-remove future-legacy-remove; do
  bash "$DRV" level "$lvl" "$repo" >/dev/null 2>&1 || true
done
bash "$TOOLKIT/drop/drop-itk-v5.sh" --apply "$repo" >/dev/null 2>&1 || true
for tok in ITK_NULLPTR itkTypeMacro ITK_DISALLOW_COPY_AND_ASSIGN CoordRepType ITKv5_CONST old_api; do
  assert_file_not_contains big.cxx "$tok"
done
assert_file_contains big.cxx nullptr
assert_file_contains big.cxx new_api
echo "PASS test_integration"
