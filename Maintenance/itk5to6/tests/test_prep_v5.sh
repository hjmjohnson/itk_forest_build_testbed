#!/usr/bin/env bash
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
T="$TOOLKIT/tasks/prep-v5"

repo="$(mk_fixture_repo)"; cd "$repo"
cat > a.cxx <<'EOF'
void f() override ITK_OVERRIDE;
auto p = ITK_NULLPTR;
int n = atoi(s);
double d = atof(s);
EOF
git add a.cxx >/dev/null
bash "$T/10-cxx11-keyword-macros.sh" "$repo" >/dev/null
bash "$T/20-atoi-atof-to-std.sh" "$repo" >/dev/null
assert_file_not_contains a.cxx ITK_NULLPTR
assert_file_not_contains a.cxx ITK_OVERRIDE
assert_file_contains a.cxx nullptr
assert_file_contains a.cxx "std::stoi"
assert_file_contains a.cxx "std::stod"

# doxygen
printf '\\doxygen{Image}\n\\subdoxygen{Foo}\n' > b.dox; git add b.dox >/dev/null
bash "$T/50-doxygen-itkref.sh" "$repo" >/dev/null
assert_file_contains b.dox '\itkref{Image}'
assert_file_contains b.dox '\itksubref{Foo}'

# cmake-lowercase: CMake files only
repo2="$(mk_fixture_repo)"; cd "$repo2"
printf 'IF(MYVAR)\n  MESSAGE("hello")\nENDIF(MYVAR)\n' > CMakeLists.txt
git add CMakeLists.txt >/dev/null
# C++ file with an uppercase token — must not be modified by the CMake-scoped task
printf 'int MESSAGE = 0;\n' > notcmake.cxx
git add notcmake.cxx >/dev/null
bash "$T/30-cmake-lowercase.sh" "$repo2" >/dev/null
assert_file_contains CMakeLists.txt 'if('
assert_file_contains CMakeLists.txt 'message('
assert_file_contains CMakeLists.txt 'endif('
assert_file_not_contains CMakeLists.txt 'IF('
assert_file_not_contains CMakeLists.txt 'MESSAGE('
assert_file_not_contains CMakeLists.txt 'ENDIF('
# MC_FILE_GLOB must not have lowercased the .cxx file
assert_file_contains notcmake.cxx 'int MESSAGE = 0;'

# cmake-blockend-cruft: else(x)->else(), endif(x)->endif()
repo3="$(mk_fixture_repo)"; cd "$repo3"
printf 'if(MYVAR)\nelse(MYVAR)\nendif(MYVAR)\n' > CMakeLists.txt
git add CMakeLists.txt >/dev/null
bash "$T/40-cmake-blockend-cruft.sh" "$repo3" >/dev/null
assert_file_contains CMakeLists.txt 'else()'
assert_file_contains CMakeLists.txt 'endif()'
assert_file_not_contains CMakeLists.txt 'else(MYVAR)'
assert_file_not_contains CMakeLists.txt 'endif(MYVAR)'

echo "PASS test_prep_v5"
