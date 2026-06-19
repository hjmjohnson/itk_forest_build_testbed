#!/usr/bin/env bash
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
T="$TOOLKIT/tasks/legacy-remove"
repo="$(mk_fixture_repo)"; cd "$repo"
cat > a.h <<'EOF'
itkTypeMacro(Foo, Superclass);
itkTypeMacroNoParent(Bar);
ITK_DISALLOW_COPY_AND_ASSIGN(Foo);
itkStaticConstMacro(Dim, unsigned int, 3);
unsigned d = itkGetStaticConstMacro(Dim);
EOF
git add a.h >/dev/null
bash "$T/10-itktypemacro.sh" "$repo" >/dev/null || true
bash "$T/20-itktypemacronoparent.sh" "$repo" >/dev/null || true
bash "$T/30-disallow-copy-and-move.sh" "$repo" >/dev/null
bash "$T/40-staticconstmacro.sh" "$repo" >/dev/null || true
bash "$T/50-getstaticconstmacro.sh" "$repo" >/dev/null || true
assert_file_contains a.h "itkOverrideGetNameOfClassMacro(Foo)"
assert_file_contains a.h "itkVirtualGetNameOfClassMacro(Bar)"
assert_file_contains a.h "ITK_DISALLOW_COPY_AND_MOVE(Foo)"
assert_file_contains a.h "static constexpr unsigned int Dim = 3"
assert_file_contains a.h "Self::Dim"
echo "PASS test_legacy_remove"
