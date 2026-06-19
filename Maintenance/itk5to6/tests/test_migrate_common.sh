#!/usr/bin/env bash
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
LIB="$TOOLKIT/lib/migrate_common.sh"

# --- mc_files_with excludes ThirdParty and finds matches ---
repo="$(mk_fixture_repo)"; cd "$repo"
mkdir -p src ThirdParty/x
printf 'ITK_NULLPTR\n' > src/a.cxx
printf 'ITK_NULLPTR\n' > ThirdParty/x/b.cxx
git add . >/dev/null
# shellcheck disable=SC1090
source "$LIB"; mc_init "$repo"
out="$(mc_files_with 'ITK_NULLPTR')"
assert_eq "src/a.cxx" "$out" "mc_files_with excludes ThirdParty"

# --- run_text_substitution_task applies, stages, is idempotent ---
repo="$(mk_fixture_repo)"; cd "$repo"
printf 'a ITK_NULLPTR b\n' > c.cxx; git add c.cxx >/dev/null
( source "$LIB"; mc_init "$repo"
  TASK_NAME="t"; TASK_LEVEL="prep-v5"; GREP_PATTERN='ITK_NULLPTR'
  SED_EXPRS=('s/ITK_NULLPTR/nullptr/g')
  COMMIT_MSG="STYLE: test"
  run_text_substitution_task >/dev/null )
assert_file_contains c.cxx nullptr
assert_file_not_contains c.cxx ITK_NULLPTR
assert_staged c.cxx
# idempotent second run -> exit 0, no change
( source "$LIB"; mc_init "$repo"
  TASK_NAME="t"; TASK_LEVEL="prep-v5"; GREP_PATTERN='ITK_NULLPTR'
  SED_EXPRS=('s/ITK_NULLPTR/nullptr/g'); COMMIT_MSG="x"
  run_text_substitution_task ) ; assert_eq 0 $? "idempotent no-op"

# --- dry-run does not modify files ---
repo="$(mk_fixture_repo)"; cd "$repo"
printf 'ITK_NULLPTR\n' > d.cxx; git add d.cxx >/dev/null
( source "$LIB"; mc_init "$repo" --dry-run
  TASK_NAME="t"; TASK_LEVEL="prep-v5"; GREP_PATTERN='ITK_NULLPTR'
  SED_EXPRS=('s/ITK_NULLPTR/nullptr/g'); COMMIT_MSG="x"
  run_text_substitution_task >/dev/null )
assert_file_contains d.cxx ITK_NULLPTR

echo "PASS test_migrate_common"
