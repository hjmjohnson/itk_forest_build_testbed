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

# atoi-atof-to-std: comment/string-aware — code converted, comments & strings verbatim
repo4="$(mk_fixture_repo)"; cd "$repo4"
cat > c.cxx <<'EOF'
int code = atoi(s);              // converts via atoi(x) historically
double d = atof(s); /* atof(y) in a block comment */
int q = std::atoi(s);
double r = std::atof(s);
const char * msg = "use atoi() here";
EOF
git add c.cxx >/dev/null
bash "$T/20-atoi-atof-to-std.sh" "$repo4" >/dev/null 2>&1
assert_file_contains c.cxx "std::stoi(s)"
assert_file_contains c.cxx "std::stod(s)"
# already-qualified std::atoi/std::atof must NOT become std::std::stoi/stod
assert_file_not_contains c.cxx "std::std::"
# comments and string literals left verbatim
assert_file_contains c.cxx "// converts via atoi(x) historically"
assert_file_contains c.cxx "/* atof(y) in a block comment */"
assert_file_contains c.cxx '"use atoi() here"'

# cmake-lowercase: report/stage only files that actually change (not every grep match)
repo5="$(mk_fixture_repo)"; cd "$repo5"
printf 'IF(A)\nENDIF(A)\n' > CMakeLists.txt          # real cmake commands -> changes
printf 'MYMACRO(x)\nUSERFUNC(y)\n' > custom.cmake    # matches grep, not builtins -> no change
git add CMakeLists.txt custom.cmake >/dev/null; git commit -qm fixture
out="$(bash "$T/30-cmake-lowercase.sh" "$repo5" 2>/dev/null)"
assert_staged CMakeLists.txt
if git diff --cached --name-only | grep -qx custom.cmake; then _fail "custom.cmake should not be staged (unchanged)"; fi
printf '%s' "$out" | grep -qF "modified and staged 1 file" || _fail "count should be 1, got: $out"
assert_file_contains custom.cmake 'MYMACRO(x)'

# clean-tree guard: an editing task refuses to run on a dirty working tree
repo6="$(mk_fixture_repo)"; cd "$repo6"
printf 'int n = atoi(s);\n' > a.cxx
printf 'tracked\n' > other.txt
git add a.cxx other.txt >/dev/null; git commit -qm base
printf 'dirty\n' >> other.txt                                    # tracked modification
bash "$T/20-atoi-atof-to-std.sh" "$repo6" >/dev/null 2>&1; rc=$?
[ "$rc" -eq 3 ] || _fail "atoi-atof must abort with 3 on a dirty tree, got $rc"
assert_file_contains a.cxx "atoi(s)"                             # untouched while aborted
if git diff --cached --name-only | grep -qx a.cxx; then _fail "nothing should be staged on a dirty-tree abort"; fi
MC_ALLOW_DIRTY=1 bash "$T/20-atoi-atof-to-std.sh" "$repo6" >/dev/null 2>&1
assert_file_contains a.cxx "std::stoi(s)"                        # override proceeds

echo "PASS test_prep_v5"
