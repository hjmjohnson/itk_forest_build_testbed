#!/usr/bin/env bash
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
T="$TOOLKIT/tasks/mandatory"
repo="$(mk_fixture_repo)"; cd "$repo"
printf 'void VerifyPreconditions() ITKv5_CONST;\n' > a.h
printf 'target_link_libraries(x GTest::GTest GTest::Main)\n' > CMakeLists.txt
git add . >/dev/null
bash "$T/10-itkv5const-to-const.sh" "$repo" >/dev/null
bash "$T/20-googletest-targets.sh" "$repo" >/dev/null
assert_file_contains a.h "void VerifyPreconditions() const;"
assert_file_not_contains a.h ITKv5_CONST
assert_file_contains CMakeLists.txt "GTest::gtest"
assert_file_contains CMakeLists.txt "GTest::gtest_main"

# Test 30-itk-cmake-targets.sh exit codes
repo="$(mk_fixture_repo)"; cd "$repo"
printf 'target_link_libraries(x ${ITK_LIBRARIES})\n' > CMakeLists.txt; git add . >/dev/null
assert_exit_code 2 bash "$T/30-itk-cmake-targets.sh" "$repo"
repo="$(mk_fixture_repo)"; cd "$repo"
printf 'int x;\n' > CMakeLists.txt; git add . >/dev/null
assert_exit_code 0 bash "$T/30-itk-cmake-targets.sh" "$repo"

# Test 40-itkdeprecated-classes.sh exit codes
repo="$(mk_fixture_repo)"; cd "$repo"
printf 'itk::Barrier b;\n' > a.cxx; git add . >/dev/null
assert_exit_code 2 bash "$T/40-itkdeprecated-classes.sh" "$repo"
repo="$(mk_fixture_repo)"; cd "$repo"
printf 'int x;\n' > a.cxx; git add . >/dev/null
assert_exit_code 0 bash "$T/40-itkdeprecated-classes.sh" "$repo"

echo "PASS test_mandatory"
