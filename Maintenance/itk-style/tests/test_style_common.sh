#!/usr/bin/env bash
# Unit tests for the shared scaffold lib/style_common.sh (no formatter binary needed).
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
# shellcheck disable=SC1090
source "$TOOLKIT/lib/style_common.sh"

STYLE_TOOL="probe"
STYLE_FILE_GLOBS=('*.py')
STYLE_EXCLUDE_RE='(^|/)(ThirdParty|Data)/|build'

# --- sc_files honors globs + excludes ---
repo="$(mk_fixture_repo)"; cd "$repo"
mkdir -p ThirdParty/x build sub Data
printf 'x\n' > a.py
printf 'x\n' > keep.py
printf 'x\n' > sub/d.py
printf 'x\n' > ThirdParty/x/b.py
printf 'x\n' > build/c.py
printf 'x\n' > Data/e.py
printf 'x\n' > notpy.txt
git add . >/dev/null
out="$(sc_files "$repo")"
printf '%s\n' "$out" > "$repo/_files.txt"
assert_file_contains "$repo/_files.txt" "a.py"
assert_file_contains "$repo/_files.txt" "keep.py"
assert_file_contains "$repo/_files.txt" "sub/d.py"
assert_file_not_contains "$repo/_files.txt" "ThirdParty/x/b.py"
assert_file_not_contains "$repo/_files.txt" "build/c.py"
assert_file_not_contains "$repo/_files.txt" "Data/e.py"
assert_file_not_contains "$repo/_files.txt" "notpy.txt"

# --- sc_repo rejects a non-git directory (sc_die -> nonzero) ---
nongit="$(mktemp -d)"
rc=0; ( STYLE_TOOL=probe; source "$TOOLKIT/lib/style_common.sh"; sc_repo "$nongit" ) >/dev/null 2>&1 || rc=$?
[ "$rc" -ne 0 ] || _fail "sc_repo should reject non-git dir"
rm -rf "$nongit"

# --- sc_repo resolves a git work tree to its top level ---
out="$(cd "$repo/sub" && sc_repo)"
assert_eq "$repo" "$out" "sc_repo returns work-tree root from a subdir"

echo "PASS test_style_common"
