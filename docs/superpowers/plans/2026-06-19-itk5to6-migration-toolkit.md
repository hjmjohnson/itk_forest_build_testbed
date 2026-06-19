# ITK v5.4.6 → v6.1 Migration Toolkit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained, semi-automated, one-task-at-a-time toolkit (bash scripts + Python helpers + agent-skills) under `Maintenance/itk5to6/` that mechanically accelerates migrating an ITK consumer from ITKv5.4.6 to ITKv6.1, emitting a suggested commit message with rationale per task and never committing or opening PRs itself.

**Architecture:** A single core library (`lib/migrate_common.sh`) carries all boilerplate — file discovery, portable sed, staging, `--dry-run`, idempotency, commit-message emission, and the main/master branch guard. Each migration is a ~15-line declarative script that sets a grep pattern, a transform, a level, and a commit message, then calls one library entry point. A driver (`itk-migrate.sh`) lists/sequences tasks by level. Drop scripts reuse a Python `#if/#elif/#else/#endif` block parser plus a maintained header↔version map. Tests are fixture-based bash assertions runnable with no external test framework.

**Tech Stack:** Bash (POSIX-leaning, GNU+BSD portable), Python 3 (drop parser, doxygen helper), git (`git grep`/`git diff`/`git add`), `sed`/`gsed`. No agent runtime dependency in the shipped scripts.

## Global Constraints

- Target floor for the v6 migration is **ITKv5.4.6**; v6.1 = current ITK `main`. (spec §1)
- Drop floors: `drop-itk-v5` keeps `ITK_VERSION_MAJOR >= 6`; `drop-itk-before-v5` keeps `>= 5`. (spec §6)
- **No script branches, commits, or opens PRs.** Apply + `git add` only; print suggested commit message. (spec §5.5, §9)
- **Branch guard:** if target repo is on `main`/`master`, prompt before editing; do not create a branch silently; do not block if human declines. (spec §9)
- Drop scripts **default to `--dry-run`**; only unambiguous blocks are auto-edited under `--apply`. (spec §6, §9)
- `ThirdParty/` is always excluded from discovery. (spec §9)
- Portability: `grep -E` not `-P`; `gsed` on macOS, `sed` on Linux, selected centrally; no BSD/GNU `sed -i` traps. (spec §9)
- Commit messages obey `commit-attribution.md` (no AI co-author trailer) and `code-comment-minimization.md` (no narration of replaced code in source comments). (spec §5.4)
- The shipped tree (`Maintenance/itk5to6/`, including `skills/`) must be self-contained bash+python, no agent runtime dependency. (spec §4, §8)
- All of `ITK/Utilities/Maintenance/migrate-itk6-code-recommendations.sh` content must be incorporated; that script is assumed removed from ITK once this lands. (spec §1)
- "Being perfect is out of scope" — scripts expose and mechanically accelerate; human intervention is expected at every step. (spec §10)
- Idempotent: re-running a task with no residual pattern is a clean no-op (exit 0). (spec §5.3)
- Exit codes: `0` applied/no-op; `2` partial/ambiguous (human review required); `1` hard error. (spec §5.7)

---

## File Structure

```
Maintenance/itk5to6/
  README.md                         # T12
  itk-migrate.sh                    # T3  driver
  lib/
    migrate_common.sh               # T2  core library (sourced by every task)
    drop_blocks.py                  # T8  #if/#elif/#else/#endif parser + floor resolver
    header_version_map.tsv          # T8  <header>\t<first-ITK-version>
  tasks/
    prep-v5/                        # T4
      10-cxx11-keyword-macros.sh
      20-atoi-atof-to-std.sh
      30-cmake-lowercase.sh
      40-cmake-blockend-cruft.sh
      50-doxygen-itkref.sh
    mandatory/                      # T5
      10-itkv5const-to-const.sh
      20-googletest-targets.sh
      30-itk-cmake-targets.sh       # assisted (uses WhatModulesITK.py)
      40-itkdeprecated-classes.sh   # assisted (report-only mapping)
    legacy-remove/                  # T6
      10-itktypemacro.sh            # regex-with-review
      20-itktypemacronoparent.sh    # regex-with-review
      30-disallow-copy-and-move.sh  # sed
      40-staticconstmacro.sh        # regex-with-review
      50-getstaticconstmacro.sh     # regex-with-review
    future-legacy-remove/           # T7
      10-coordrep-to-coordinate.sh  # sed
  manual/                           # T10
    threaded-generate-data.sh
    multithreader-backends.sh
    barrier-to-parallelize.sh
    mutex-atomic-to-std.sh
    stl-replacements.sh
    spatialobject-space.sh
    verify-const-qualifier.sh
    python-cleanups.sh
    vtk-version-bump.sh
    cmake-cxx-floor.sh
  drop/
    drop-itk-v5.sh                  # T9
    drop-itk-before-v5.sh           # T9
  commit-messages/                  # generated at runtime (.msg files); .gitkeep committed
  skills/
    itk-migrate-v6/SKILL.md         # T11
    itk-drop-version/SKILL.md       # T11
  tests/
    run_tests.sh                    # T1  harness
    helpers.sh                      # T1  assert_* + fixture-repo factory
    fixtures/                       # per-test sample inputs created inline by tests
    test_*.sh                       # one per task
```

**Responsibility boundaries:** `lib/migrate_common.sh` owns all side effects and git interaction; task scripts are pure declarations; the driver owns sequencing/UX; `drop_blocks.py` owns preprocessor parsing; the test harness owns isolation (each test builds a throwaway git repo in a temp dir).

---

## Task 1: Test harness + scaffolding

**Files:**
- Create: `Maintenance/itk5to6/tests/helpers.sh`
- Create: `Maintenance/itk5to6/tests/run_tests.sh`
- Create: `Maintenance/itk5to6/commit-messages/.gitkeep`
- Test: the harness self-tests via a trivial sample test

**Interfaces:**
- Produces (sourced by all `tests/test_*.sh`):
  - `mk_fixture_repo` — creates a temp dir, `git init -q`, sets a throwaway `user.name`/`user.email`, prints the path on stdout. Caller `cd`s into it.
  - `assert_eq EXPECTED ACTUAL [msg]` — exits the test nonzero on mismatch, prints a diff.
  - `assert_file_contains FILE NEEDLE` / `assert_file_not_contains FILE NEEDLE`
  - `assert_exit_code EXPECTED CMD...` — runs CMD, compares `$?`.
  - `assert_staged FILE` — asserts `git diff --cached --name-only` lists FILE.
  - `TOOLKIT` env var — absolute path to `Maintenance/itk5to6`.

- [ ] **Step 1: Write the failing self-test**

Create `Maintenance/itk5to6/tests/test_harness_selftest.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/helpers.sh"

repo="$(mk_fixture_repo)"
cd "$repo"
printf 'hello\n' > a.txt
git add a.txt
assert_staged a.txt
assert_file_contains a.txt hello
assert_file_not_contains a.txt goodbye
assert_exit_code 0 true
assert_exit_code 1 false
echo "PASS test_harness_selftest"
```

- [ ] **Step 2: Run it to verify it fails (helpers not written yet)**

Run: `bash Maintenance/itk5to6/tests/test_harness_selftest.sh`
Expected: FAIL — `helpers.sh: No such file or directory`.

- [ ] **Step 3: Implement `tests/helpers.sh`**

```bash
#!/usr/bin/env bash
# Shared test helpers. No external test framework required.
TOOLKIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export TOOLKIT

mk_fixture_repo() {
  local d
  d="$(mktemp -d "${TMPDIR:-/tmp}/itk5to6-fixture.XXXXXX")"
  git -C "$d" init -q
  git -C "$d" config user.name  "itk5to6 test"
  git -C "$d" config user.email "itk5to6@example.invalid"
  git -C "$d" config commit.gpgsign false
  printf '%s\n' "$d"
}

_fail() { printf 'ASSERT FAIL: %s\n' "$*" >&2; exit 1; }

assert_eq() {
  local expected="$1" actual="$2" msg="${3:-}"
  if [ "$expected" != "$actual" ]; then
    printf 'expected: %s\nactual:   %s\n' "$expected" "$actual" >&2
    _fail "${msg:-assert_eq}"
  fi
}

assert_file_contains() {
  grep -qF -- "$2" "$1" || _fail "file $1 missing: $2"
}
assert_file_not_contains() {
  if grep -qF -- "$2" "$1"; then _fail "file $1 unexpectedly contains: $2"; fi
}

assert_exit_code() {
  local expected="$1"; shift
  local rc=0
  "$@" >/dev/null 2>&1 || rc=$?
  assert_eq "$expected" "$rc" "exit code of: $*"
}

assert_staged() {
  git diff --cached --name-only | grep -qx -- "$1" || _fail "not staged: $1"
}
```

- [ ] **Step 4: Run the self-test to verify it passes**

Run: `bash Maintenance/itk5to6/tests/test_harness_selftest.sh`
Expected: `PASS test_harness_selftest`

- [ ] **Step 5: Implement `tests/run_tests.sh` (discovers and runs all `test_*.sh`)**

```bash
#!/usr/bin/env bash
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
fail=0; pass=0
for t in "$here"/test_*.sh; do
  if bash "$t"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAILED: $t"; fi
done
printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
```

- [ ] **Step 6: Add `commit-messages/.gitkeep` and run the full suite**

Run: `touch Maintenance/itk5to6/commit-messages/.gitkeep && bash Maintenance/itk5to6/tests/run_tests.sh`
Expected: `1 passed, 0 failed`

- [ ] **Step 7: Commit**

```bash
git add Maintenance/itk5to6/tests Maintenance/itk5to6/commit-messages/.gitkeep
git commit -m "ENH: itk5to6 migration toolkit test harness and scaffolding"
```

---

## Task 2: Core library `lib/migrate_common.sh`

**Files:**
- Create: `Maintenance/itk5to6/lib/migrate_common.sh`
- Test: `Maintenance/itk5to6/tests/test_migrate_common.sh`

**Interfaces:**
- Consumes: nothing (foundation).
- Produces (sourced by every task script and the driver):
  - `mc_init "$@"` — parses common args, sets globals: `MC_DRY_RUN` (0/1), `MC_STAGE` (0/1), `MC_REPO` (abs path, default `$PWD` or first non-flag arg), `SED` (sed|gsed). `cd`s into `MC_REPO`. Recognizes `--dry-run`, `--no-stage`, and a trailing path.
  - `mc_sed_bin` — echoes `gsed` if present on macOS else `sed`.
  - `mc_files_with PATTERN` — prints newline-separated tracked files matching PATTERN via `git grep -lE`, excluding `ThirdParty/`. Empty output if none.
  - `mc_apply_sed EXPR FILE...` — portable in-place edit (handles BSD vs GNU).
  - `mc_stage FILE...` — `git add` unless `MC_STAGE=0`.
  - `mc_branch_guard` — if current branch is `main`/`master` and stdin is a TTY, prompt "Edit on <branch>? Create a working branch first? [c=create/e=edit/a=abort]"; on `c` print the suggested `git switch -c` command and abort (return 1, so the caller's `|| return 1` halts; human acts); on `a` abort code 1; on `e` proceed. Non-TTY: print a warning and proceed.
  - `mc_emit_commit_message TASK LEVEL` — writes `$MC_REPO`-independent message (from global `COMMIT_MSG`) to `commit-messages/<TASK>.msg` under the toolkit dir and echoes it to stdout, framed.
  - `run_text_substitution_task` — uses globals `TASK_NAME`, `TASK_LEVEL`, `GREP_PATTERN`, `SED_EXPRS` (array); finds files, in dry-run prints `git diff` preview, else applies each sed expr + stages; idempotency no-op when no files; emits commit message; returns 0.
  - `run_regex_review_task` — like above plus a global `RESIDUAL_PATTERN`; after applying, re-scans and prints any `file:line` still matching `RESIDUAL_PATTERN`; returns 2 if residuals exist, else 0.

- [ ] **Step 1: Write failing tests**

Create `Maintenance/itk5to6/tests/test_migrate_common.sh`:

```bash
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
```

- [ ] **Step 2: Run to verify failure**

Run: `bash Maintenance/itk5to6/tests/test_migrate_common.sh`
Expected: FAIL — `migrate_common.sh: No such file or directory`.

- [ ] **Step 3: Implement `lib/migrate_common.sh`**

```bash
#!/usr/bin/env bash
# Core library for itk5to6 migration task scripts. Source, then set the
# declarative globals and call run_text_substitution_task / run_regex_review_task.
# Never commits, branches, or runs gh.

mc_sed_bin() {
  if [ "$(uname -s)" = "Darwin" ] && command -v gsed >/dev/null 2>&1; then
    printf 'gsed\n'
  else
    printf 'sed\n'
  fi
}

mc_init() {
  MC_DRY_RUN=0; MC_STAGE=1; MC_REPO=""
  SED="$(mc_sed_bin)"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --dry-run) MC_DRY_RUN=1 ;;
      --no-stage) MC_STAGE=0 ;;
      --apply) MC_DRY_RUN=0 ;;
      -*) printf 'unknown flag: %s\n' "$1" >&2; return 1 ;;
      *) MC_REPO="$1" ;;
    esac
    shift
  done
  [ -n "$MC_REPO" ] || MC_REPO="$PWD"
  MC_REPO="$(cd "$MC_REPO" && pwd)"
  cd "$MC_REPO" || return 1
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    printf 'not a git work tree: %s\n' "$MC_REPO" >&2; return 1; }
  # toolkit dir for writing .msg files
  MC_TOOLKIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
}

mc_files_with() {
  git grep -lE -- "$1" 2>/dev/null | grep -vE '(^|/)ThirdParty/' || true
}

mc_apply_sed() {
  local expr="$1"; shift
  if [ "$SED" = "sed" ] && sed --version >/dev/null 2>&1; then
    "$SED" -i -e "$expr" "$@"          # GNU
  else
    "$SED" -i '' -e "$expr" "$@"       # BSD
  fi
}

mc_stage() {
  [ "$MC_STAGE" -eq 1 ] || return 0
  git add -- "$@"
}

mc_branch_guard() {
  local br; br="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"
  case "$br" in
    main|master)
      if [ -t 0 ]; then
        printf 'On branch %s. [c]reate working branch / [e]dit here / [a]bort? ' "$br" >&2
        read -r ans
        case "$ans" in
          c|C) printf 'Run:  git switch -c itk5to6-migration\nThen re-run.\n' >&2; return 1 ;;
          a|A) printf 'aborted\n' >&2; return 1 ;;
          *) return 0 ;;
        esac
      else
        printf 'WARNING: editing on %s (non-interactive); proceeding.\n' "$br" >&2
      fi
      ;;
  esac
  return 0
}

mc_emit_commit_message() {
  local task="$1"
  local out="$MC_TOOLKIT/commit-messages/${task}.msg"
  printf '%s\n' "$COMMIT_MSG" > "$out"
  printf '\n----- suggested commit message (also written to %s) -----\n' "$out"
  printf '%s\n' "$COMMIT_MSG"
  printf -- '----- the human reviews, validates (pre-commit), and commits -----\n'
}

run_text_substitution_task() {
  mc_branch_guard || return 1
  local files; files="$(mc_files_with "$GREP_PATTERN")"
  if [ -z "$files" ]; then
    printf '[%s] nothing to do (no %s)\n' "$TASK_NAME" "$GREP_PATTERN"
    return 0
  fi
  # shellcheck disable=SC2206
  local farr=(); while IFS= read -r f; do farr+=("$f"); done <<< "$files"
  if [ "$MC_DRY_RUN" -eq 1 ]; then
    printf '[%s] DRY RUN; would modify %d file(s):\n' "$TASK_NAME" "${#farr[@]}"
    local tmp expr
    for f in "${farr[@]}"; do
      tmp="$(mktemp)"; cp "$f" "$tmp"
      for expr in "${SED_EXPRS[@]}"; do mc_apply_sed "$expr" "$tmp"; done
      diff -u "$f" "$tmp" | sed "s|$tmp|$f (proposed)|" || true
      rm -f "$tmp"
    done
    return 0
  fi
  local expr
  for expr in "${SED_EXPRS[@]}"; do mc_apply_sed "$expr" "${farr[@]}"; done
  mc_stage "${farr[@]}"
  printf '[%s] modified and staged %d file(s).\n' "$TASK_NAME" "${#farr[@]}"
  mc_emit_commit_message "$TASK_NAME"
  return 0
}

run_regex_review_task() {
  run_text_substitution_task
  [ "$MC_DRY_RUN" -eq 1 ] && return 0
  local residual; residual="$(git grep -nE -- "${RESIDUAL_PATTERN:-$GREP_PATTERN}" 2>/dev/null | grep -vE '(^|/)ThirdParty/' || true)"
  if [ -n "$residual" ]; then
    printf '\n[%s] WARNING: review these residual sites (regex could not fully transform):\n%s\n' "$TASK_NAME" "$residual"
    return 2
  fi
  return 0
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `bash Maintenance/itk5to6/tests/test_migrate_common.sh`
Expected: `PASS test_migrate_common`

- [ ] **Step 5: Commit**

```bash
git add Maintenance/itk5to6/lib/migrate_common.sh Maintenance/itk5to6/tests/test_migrate_common.sh
git commit -m "ENH: itk5to6 core migration library (discovery, sed, staging, dry-run, branch guard)"
```

---

## Task 3: Driver `itk-migrate.sh`

**Files:**
- Create: `Maintenance/itk5to6/itk-migrate.sh`
- Test: `Maintenance/itk5to6/tests/test_driver.sh`

**Interfaces:**
- Consumes: task scripts under `tasks/<level>/NN-*.sh`; `lib/migrate_common.sh` for `status` grep patterns (reads each task's `GREP_PATTERN` by sourcing in a subshell).
- Produces (CLI):
  - `itk-migrate.sh list [--level prep-v5|mandatory|legacy-remove|future-legacy-remove|manual]`
  - `itk-migrate.sh status [path]` — for each task prints `PENDING`/`clean` based on `GREP_PATTERN`.
  - `itk-migrate.sh run <task-name> [--dry-run|--no-stage] [path]` — runs one task by basename (with or without `NN-` prefix / `.sh`).
  - `itk-migrate.sh level <level> [--dry-run] [--build-check "cmd"] [path]` — runs each task in order, pausing; on `--build-check`, runs cmd between tasks and stops on nonzero.

- [ ] **Step 1: Write failing tests**

Create `Maintenance/itk5to6/tests/test_driver.sh`:

```bash
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

echo "PASS test_driver"
```

(Note: `assert_file_contains <(...)` uses process substitution — the helper greps a path; bash provides `/dev/fd/NN`.)

- [ ] **Step 2: Run to verify failure**

Run: `bash Maintenance/itk5to6/tests/test_driver.sh`
Expected: FAIL — driver missing.

- [ ] **Step 3: Implement `itk-migrate.sh`**

```bash
#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LEVELS="prep-v5 mandatory legacy-remove future-legacy-remove"

_task_files() {  # $1 optional level filter
  local lvl="${1:-}"
  if [ -n "$lvl" ] && [ "$lvl" != "manual" ]; then
    ls "$HERE/tasks/$lvl"/*.sh 2>/dev/null
  elif [ "$lvl" = "manual" ]; then
    ls "$HERE/manual"/*.sh 2>/dev/null
  else
    ls "$HERE"/tasks/*/*.sh 2>/dev/null
  fi
}

_task_meta() {  # echoes "name<TAB>level<TAB>pattern" by sourcing in a subshell
  local f="$1"
  ( TASK_NAME=""; TASK_LEVEL=""; GREP_PATTERN=""
    # shellcheck disable=SC1090
    MC_META_ONLY=1 source "$f" 2>/dev/null
    printf '%s\t%s\t%s\n' "$TASK_NAME" "$TASK_LEVEL" "$GREP_PATTERN" )
}

cmd="${1:-help}"; shift || true
case "$cmd" in
  list)
    lvl=""; [ "${1:-}" = "--level" ] && lvl="$2"
    for f in $(_task_files "$lvl"); do
      IFS=$'\t' read -r n l _ < <(_task_meta "$f")
      printf '%-28s [%s]\n' "$n" "$l"
    done
    ;;
  status)
    path="${1:-$PWD}"
    for f in $(_task_files ""); do
      IFS=$'\t' read -r n _ p < <(_task_meta "$f")
      if git -C "$path" grep -qE -- "$p" -- ':!*ThirdParty/*' 2>/dev/null; then
        printf '%-28s PENDING\n' "$n"
      else
        printf '%-28s clean\n' "$n"
      fi
    done
    ;;
  run)
    name="$1"; shift
    f="$(_task_files "" | while read -r x; do
          IFS=$'\t' read -r n _ _ < <(_task_meta "$x"); [ "$n" = "$name" ] && echo "$x"; done | head -1)"
    [ -n "$f" ] || { echo "no such task: $name" >&2; exit 1; }
    bash "$f" "$@"
    ;;
  level)
    lvl="$1"; shift
    build_check=""; passthru=()
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --build-check) build_check="$2"; shift 2 ;;
        *) passthru+=("$1"); shift ;;
      esac
    done
    for f in $(_task_files "$lvl"); do
      IFS=$'\t' read -r n _ _ < <(_task_meta "$f")
      printf '\n=== %s ===\n' "$n"
      bash "$f" "${passthru[@]}" || true
      if [ -n "$build_check" ]; then
        printf '... build-check: %s\n' "$build_check"
        ( eval "$build_check" ) || { echo "build-check FAILED after $n; stopping." >&2; exit 1; }
      fi
    done
    ;;
  *)
    cat <<EOF
itk-migrate.sh — semi-automated ITK v5.4.6 -> v6.1 migration driver
  list [--level L]                 list tasks
  status [path]                    show pending/clean per task
  run <task> [--dry-run|--no-stage] [path]
  level <L> [--dry-run] [--build-check "cmd"] [path]
Levels: $LEVELS manual
EOF
    ;;
esac
```

- [ ] **Step 4: Add the `MC_META_ONLY` early-return to the library**

Modify `lib/migrate_common.sh` — at the very top of `run_text_substitution_task` and `run_regex_review_task`, add:

```bash
  [ "${MC_META_ONLY:-0}" = "1" ] && return 0
```

This lets the driver source a task to read its metadata without executing it.

- [ ] **Step 5: Run tests** (will still fail until at least one task exists; create a temporary stub)

Create stub `Maintenance/itk5to6/tasks/legacy-remove/30-disallow-copy-and-move.sh` minimally (final version lands in Task 6):

```bash
#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="disallow-copy-and-move"; TASK_LEVEL="legacy-remove"
GREP_PATTERN='ITK_DISALLOW_COPY_AND_ASSIGN'
SED_EXPRS=('s/ITK_DISALLOW_COPY_AND_ASSIGN/ITK_DISALLOW_COPY_AND_MOVE/g')
COMMIT_MSG="STYLE: Rename ITK_DISALLOW_COPY_AND_ASSIGN to ITK_DISALLOW_COPY_AND_MOVE"
mc_init "$@"
run_text_substitution_task
```

Run: `bash Maintenance/itk5to6/tests/test_driver.sh`
Expected: `PASS test_driver`

- [ ] **Step 6: Commit**

```bash
git add Maintenance/itk5to6/itk-migrate.sh Maintenance/itk5to6/lib/migrate_common.sh \
        Maintenance/itk5to6/tasks/legacy-remove/30-disallow-copy-and-move.sh \
        Maintenance/itk5to6/tests/test_driver.sh
git commit -m "ENH: itk5to6 driver (list/status/run/level) with metadata introspection"
```

---

## Task 4: prep-v5 task scripts

**Files:**
- Create: `Maintenance/itk5to6/tasks/prep-v5/10-cxx11-keyword-macros.sh`
- Create: `Maintenance/itk5to6/tasks/prep-v5/20-atoi-atof-to-std.sh`
- Create: `Maintenance/itk5to6/tasks/prep-v5/30-cmake-lowercase.sh`
- Create: `Maintenance/itk5to6/tasks/prep-v5/40-cmake-blockend-cruft.sh`
- Create: `Maintenance/itk5to6/tasks/prep-v5/50-doxygen-itkref.sh`
- Test: `Maintenance/itk5to6/tests/test_prep_v5.sh`

**Interfaces:**
- Consumes: `lib/migrate_common.sh` (`mc_init`, `run_text_substitution_task`).
- Produces: 5 runnable task scripts conforming to the task contract.

**The sed expressions (verbatim from `ReplaceOutdatedMacroNames.sh`, `replace_atoi_atof.sh`, `cmakeToLowerCase.sh`, `cmakeRemoveBlockEndCruft.sh`, `update_doxygen_for_itkv6.py`):**

10-cxx11-keyword-macros `SED_EXPRS` (order matters — `OR_THROW` and `_EXPR` before bare):
```
s/ITK_NOEXCEPT_OR_THROW/ITK_NOEXCEPT/g
s/ITK_HAS_CXX11_STATIC_ASSERT/ITK_COMPILER_CXX_STATIC_ASSERT/g
s/ITK_DELETE_FUNCTION/ITK_DELETED_FUNCTION/g
s/ITK_HAS_CPP11_ALIGNAS/ITK_COMPILER_CXX_ALIGNAS/g
s/ITK_ALIGNAS/alignas/g
s/ITK_ALIGNOF/alignof/g
s/ITK_CONSTEXPR/constexpr/g
s/ITK_EXTERN_TEMPLATE/extern/g
s/ITK_FINAL/final/g
s/ITK_NOEXCEPT_EXPR/noexcept/g
s/ITK_NOEXCEPT/noexcept/g
s/ITK_NULLPTR/nullptr/g
s/ITK_OVERRIDE/override/g
s/ITK_THREAD_LOCAL/thread_local/g
```
`GREP_PATTERN='ITK_(NULLPTR|OVERRIDE|FINAL|CONSTEXPR|NOEXCEPT|ALIGNAS|ALIGNOF|EXTERN_TEMPLATE|THREAD_LOCAL|DELETE_FUNCTION|NOEXCEPT_OR_THROW)'`

20-atoi-atof: `SED_EXPRS=('s/\batoi *(/std::stoi(/g' 's/\batof *(/std::stod(/g')`, `GREP_PATTERN='\b(atoi|atof) *\('`

30-cmake-lowercase / 40-cmake-blockend: CMake-only; restrict discovery to `CMakeLists.txt`/`*.cmake`. These override discovery by setting `GREP_PATTERN` to a CMake construct and adding a `MC_FILE_GLOB` filter (add support in lib — see Step 6).

50-doxygen: `SED_EXPRS=('s/\\\\doxygen{/\\\\itkref{/g' 's/\\\\subdoxygen{/\\\\itksubref{/g')`, `GREP_PATTERN='\\\\(sub)?doxygen\{'`

**Commit messages** (each script's `COMMIT_MSG`):

- [ ] **Step 1: Write failing test**

Create `Maintenance/itk5to6/tests/test_prep_v5.sh`:

```bash
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
echo "PASS test_prep_v5"
```

- [ ] **Step 2: Run to verify failure**

Run: `bash Maintenance/itk5to6/tests/test_prep_v5.sh`
Expected: FAIL — scripts missing.

- [ ] **Step 3: Write `10-cxx11-keyword-macros.sh`**

```bash
#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="cxx11-keyword-macros"; TASK_LEVEL="prep-v5"
GREP_PATTERN='ITK_(NULLPTR|OVERRIDE|FINAL|CONSTEXPR|NOEXCEPT|ALIGNAS|ALIGNOF|EXTERN_TEMPLATE|THREAD_LOCAL|DELETE_FUNCTION|NOEXCEPT_OR_THROW)'
SED_EXPRS=(
  's/ITK_NOEXCEPT_OR_THROW/ITK_NOEXCEPT/g'
  's/ITK_HAS_CXX11_STATIC_ASSERT/ITK_COMPILER_CXX_STATIC_ASSERT/g'
  's/ITK_DELETE_FUNCTION/ITK_DELETED_FUNCTION/g'
  's/ITK_HAS_CPP11_ALIGNAS/ITK_COMPILER_CXX_ALIGNAS/g'
  's/ITK_ALIGNAS/alignas/g' 's/ITK_ALIGNOF/alignof/g'
  's/ITK_CONSTEXPR/constexpr/g' 's/ITK_EXTERN_TEMPLATE/extern/g'
  's/ITK_FINAL/final/g' 's/ITK_NOEXCEPT_EXPR/noexcept/g'
  's/ITK_NOEXCEPT/noexcept/g' 's/ITK_NULLPTR/nullptr/g'
  's/ITK_OVERRIDE/override/g' 's/ITK_THREAD_LOCAL/thread_local/g'
)
read -r -d '' COMMIT_MSG <<'EOF' || true
STYLE: Replace deprecated ITK C++11 compatibility macros with keywords

ITK requires C++17, so the C++11-era portability macros (ITK_NULLPTR,
ITK_OVERRIDE, ITK_CONSTEXPR, ITK_NOEXCEPT, ITK_FINAL, ITK_ALIGNAS,
ITK_ALIGNOF, ITK_EXTERN_TEMPLATE, ITK_THREAD_LOCAL, ITK_DELETED_FUNCTION)
are unconditionally identical to their standard keywords. Using the
keywords directly removes a layer of indirection and matches modern ITK.
EOF
mc_init "$@"
run_text_substitution_task
```

- [ ] **Step 4: Write `20-atoi-atof-to-std.sh`**

```bash
#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="atoi-atof-to-std"; TASK_LEVEL="prep-v5"
GREP_PATTERN='\b(atoi|atof) *\('
SED_EXPRS=('s/\batoi *(/std::stoi(/g' 's/\batof *(/std::stod(/g')
read -r -d '' COMMIT_MSG <<'EOF' || true
ENH: Replace atoi/atof with std::stoi/std::stod

std::stoi/std::stod throw std::invalid_argument on malformed input
instead of silently returning 0, surfacing parse errors that atoi/atof
hide. Requires <string>. Review call sites that relied on the silent-0
behavior.
EOF
mc_init "$@"
run_regex_review_task   # flags any atoi/atof left inside identifiers
```

- [ ] **Step 5: Write `50-doxygen-itkref.sh`**

```bash
#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="doxygen-itkref"; TASK_LEVEL="prep-v5"
GREP_PATTERN='\\(sub)?doxygen\{'
SED_EXPRS=('s/\\doxygen{/\\itkref{/g' 's/\\subdoxygen{/\\itksubref{/g')
read -r -d '' COMMIT_MSG <<'EOF' || true
DOC: Update \doxygen / \subdoxygen aliases to \itkref / \itksubref

ITKv6 renames the Doxygen aliases. \itkref{} and \itksubref{} are the
ITKv6 spellings; the old aliases no longer resolve.
EOF
mc_init "$@"
run_text_substitution_task
```

- [ ] **Step 6: Add `MC_FILE_GLOB` discovery filter to the library, then write the two CMake scripts**

Modify `mc_files_with` in `lib/migrate_common.sh` to honor an optional `MC_FILE_GLOB` (pathspec) global:

```bash
mc_files_with() {
  if [ -n "${MC_FILE_GLOB:-}" ]; then
    git grep -lE -- "$1" -- $MC_FILE_GLOB 2>/dev/null | grep -vE '(^|/)ThirdParty/' || true
  else
    git grep -lE -- "$1" 2>/dev/null | grep -vE '(^|/)ThirdParty/' || true
  fi
}
```

Write `30-cmake-lowercase.sh` and `40-cmake-blockend-cruft.sh` setting
`MC_FILE_GLOB='*.cmake CMakeLists.txt'`. `30` generates per-command
lowercase sed expressions from the upstream command list (port the loop in
`cmakeToLowerCase.sh`); `40` applies `s/\b(else|endif|endforeach|endfunction|endmacro|endwhile)\b[[:space:]]*([^)]*)/\1()/g`.
Commit messages:
```
STYLE: Lowercase CMake commands  (rationale: modern CMake style; case-insensitive but lowercase is the convention)
STYLE: Drop block-end command arguments (else(x)->else())  (rationale: the args are ignored by CMake and drift from the opening condition)
```

- [ ] **Step 7: Run tests to verify pass**

Run: `bash Maintenance/itk5to6/tests/test_prep_v5.sh && bash Maintenance/itk5to6/tests/run_tests.sh`
Expected: `PASS test_prep_v5` and overall `N passed, 0 failed`.

- [ ] **Step 8: Commit**

```bash
git add Maintenance/itk5to6/tasks/prep-v5 Maintenance/itk5to6/lib/migrate_common.sh Maintenance/itk5to6/tests/test_prep_v5.sh
git commit -m "ENH: itk5to6 prep-v5 tasks (C++11 macros, atoi/atof, CMake, doxygen)"
```

---

## Task 5: L1 mandatory task scripts

**Files:**
- Create: `Maintenance/itk5to6/tasks/mandatory/10-itkv5const-to-const.sh`
- Create: `Maintenance/itk5to6/tasks/mandatory/20-googletest-targets.sh`
- Create: `Maintenance/itk5to6/tasks/mandatory/30-itk-cmake-targets.sh` (assisted)
- Create: `Maintenance/itk5to6/tasks/mandatory/40-itkdeprecated-classes.sh` (report-only)
- Test: `Maintenance/itk5to6/tests/test_mandatory.sh`

**Interfaces:**
- Consumes: `lib/migrate_common.sh`.
- Produces: 4 task scripts. `30`/`40` are assisted: they apply safe renames and print a guidance/report block (exit 2 when manual follow-up is needed).

- [ ] **Step 1: Failing test**

```bash
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
echo "PASS test_mandatory"
```

- [ ] **Step 2: Run to verify failure** — Run: `bash Maintenance/itk5to6/tests/test_mandatory.sh` → FAIL.

- [ ] **Step 3: Write `10-itkv5const-to-const.sh`** (sed `s/ITKv5_CONST/const/g`, `GREP_PATTERN='ITKv5_CONST'`)

```bash
#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="itkv5const-to-const"; TASK_LEVEL="mandatory"
GREP_PATTERN='ITKv5_CONST'
SED_EXPRS=('s/ITKv5_CONST/const/g')
read -r -d '' COMMIT_MSG <<'EOF' || true
ENH: Replace ITKv5_CONST with const

ITKv5_CONST bridged the const-qualifier added to ProcessObject::
VerifyPreconditions() and VerifyInputInformation() in ITKv5 while keeping
ITKv4 compilable. ITKv6 removes ITKV4_COMPATIBILITY and the macro, so the
const qualifier is now unconditional.
EOF
mc_init "$@"
run_text_substitution_task
```

- [ ] **Step 4: Write `20-googletest-targets.sh`** (`MC_FILE_GLOB='*.cmake CMakeLists.txt'`; `SED_EXPRS=('s/GTest::GTest/GTest::gtest/g' 's/GTest::Main/GTest::gtest_main/g')`; `GREP_PATTERN='GTest::(GTest|Main)'`; commit msg `COMP: Use lowercase GoogleTest imported targets (GTest::gtest / GTest::gtest_main)` with rationale that ITKv6's bundled GTest exports the lowercase target names).

- [ ] **Step 5: Write `30-itk-cmake-targets.sh` (assisted)** — `MC_FILE_GLOB='*.cmake CMakeLists.txt'`; detect `${ITK_LIBRARIES}` and `include(${ITK_USE_FILE})`; print guidance to replace with `ITK::` namespaced module targets and to run `WhatModulesITK.py` to enumerate needed modules; apply the trivial `include(${ITK_USE_FILE})` removal only when paired with a `find_package(ITK)`; return 2 with a per-file report. Commit msg `COMP: Link ITK via namespaced ITK:: targets instead of ITK_LIBRARIES/ITK_USE_FILE`.

- [ ] **Step 6: Write `40-itkdeprecated-classes.sh` (report-only)** — `GREP_PATTERN='itk::(TreeNode|Barrier|VectorResampleImageFilter|...)'`; never edits; prints each hit with the recommended replacement from a small inline map; returns 2. Commit msg not emitted (no edit).

- [ ] **Step 7: Run tests** — `bash Maintenance/itk5to6/tests/test_mandatory.sh` → `PASS test_mandatory`.

- [ ] **Step 8: Commit**

```bash
git add Maintenance/itk5to6/tasks/mandatory Maintenance/itk5to6/tests/test_mandatory.sh
git commit -m "ENH: itk5to6 L1 mandatory tasks (ITKv5_CONST, GTest targets, ITK:: targets, deprecated-class report)"
```

---

## Task 6: L2 ITK_LEGACY_REMOVE task scripts

**Files:**
- Create: `Maintenance/itk5to6/tasks/legacy-remove/10-itktypemacro.sh`
- Create: `Maintenance/itk5to6/tasks/legacy-remove/20-itktypemacronoparent.sh`
- Replace stub: `Maintenance/itk5to6/tasks/legacy-remove/30-disallow-copy-and-move.sh`
- Create: `Maintenance/itk5to6/tasks/legacy-remove/40-staticconstmacro.sh`
- Create: `Maintenance/itk5to6/tasks/legacy-remove/50-getstaticconstmacro.sh`
- Test: `Maintenance/itk5to6/tests/test_legacy_remove.sh`

**Interfaces:**
- Consumes: `lib/migrate_common.sh` (`run_regex_review_task` for the 3 arg-reordering macros).
- Produces: 5 task scripts. The regex-with-review ones set `RESIDUAL_PATTERN` to detect transforms the regex could not handle (e.g. multi-line macro invocations).

**Verbatim regexes (from `migrate-itk6-code-recommendations.sh`):**
```
10: s/itkTypeMacro *(\(.*\),.*) *;/itkOverrideGetNameOfClassMacro(\1);/g
20: s/itkTypeMacroNoParent *(\(.*\),.*) *;/itkVirtualGetNameOfClassMacro(\1);/g
30: s/ITK_DISALLOW_COPY_AND_ASSIGN/ITK_DISALLOW_COPY_AND_MOVE/g
40: s/itkStaticConstMacro *( *\([^,]*\),[ \_s]*\([^,]*\),[ \_s]*\([^)]*\)) */static constexpr \2 \1 = \3/g
50: s/itkGetStaticConstMacro *(\(.*\))/Self::\1/g
```
`RESIDUAL_PATTERN` for 10/20/40/50 = the macro name itself (any leftover = a site the single-line regex missed → review).

- [ ] **Step 1: Failing test**

```bash
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
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Write the 5 scripts** using the verbatim regexes above. `10/20/40/50` call `run_regex_review_task` with `RESIDUAL_PATTERN='itkTypeMacro'` etc.; `30` calls `run_text_substitution_task`. Commit messages are the full provenance-bearing messages copied verbatim from `migrate-itk6-code-recommendations.sh` lines 62-76 (itkOverride/Virtual), 95-103 (DISALLOW), 123-141 (staticconst). Example for `10`:

```bash
read -r -d '' COMMIT_MSG <<'EOF' || true
STYLE: Add itkVirtualGetNameOfClassMacro + itkOverrideGetNameOfClassMacro

Added two new macros, intended to replace the old 'itkTypeMacro' and
'itkTypeMacroNoParent'. The aim is to be clearer about what they do: add
a virtual 'GetNameOfClass()' member function and override it. Unlike
'itkTypeMacro', 'itkOverrideGetNameOfClassMacro' has no 'superclass'
parameter, which was never used. Removed when ITK_LEGACY_REMOVE is ON.
EOF
```

- [ ] **Step 4: Run tests** → `PASS test_legacy_remove`.

- [ ] **Step 5: Commit**

```bash
git add Maintenance/itk5to6/tasks/legacy-remove Maintenance/itk5to6/tests/test_legacy_remove.sh
git commit -m "ENH: itk5to6 L2 ITK_LEGACY_REMOVE tasks (TypeMacro, DISALLOW_COPY, StaticConstMacro)"
```

---

## Task 7: L3 ITK_FUTURE_LEGACY_REMOVE task script

**Files:**
- Create: `Maintenance/itk5to6/tasks/future-legacy-remove/10-coordrep-to-coordinate.sh`
- Test: `Maintenance/itk5to6/tests/test_future_legacy_remove.sh`

**Interfaces:** Consumes `lib/migrate_common.sh`; produces one task script.

Verbatim sed order (specific before general):
```
s/ImagePointCoordRepType/ImagePointCoordinateType/g
s/InputCoordRepType/InputCoordinateType/g
s/OutputCoordRepType/OutputCoordinateType/g
s/CoordRepType/CoordinateType/g
```

- [ ] **Step 1: Failing test**

```bash
#!/usr/bin/env bash
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
T="$TOOLKIT/tasks/future-legacy-remove"
repo="$(mk_fixture_repo)"; cd "$repo"
printf 'using X = CoordRepType; using Y = InputCoordRepType;\n' > a.h; git add a.h >/dev/null
bash "$T/10-coordrep-to-coordinate.sh" "$repo" >/dev/null
assert_file_contains a.h "CoordinateType"
assert_file_contains a.h "InputCoordinateType"
assert_file_not_contains a.h "CoordRepType"
echo "PASS test_future_legacy_remove"
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Write the script** with the 4 ordered sed expressions, `GREP_PATTERN='CoordRepType'`, and the verbatim commit message from `migrate-itk6-code-recommendations.sh` lines 189-198 (CoordRepType -> CoordinateType, removed when ITK_FUTURE_LEGACY_REMOVE enabled).

- [ ] **Step 4: Run tests** → `PASS test_future_legacy_remove`.

- [ ] **Step 5: Commit**

```bash
git add Maintenance/itk5to6/tasks/future-legacy-remove Maintenance/itk5to6/tests/test_future_legacy_remove.sh
git commit -m "ENH: itk5to6 L3 ITK_FUTURE_LEGACY_REMOVE task (CoordRepType -> CoordinateType)"
```

---

## Task 8: Drop infrastructure — `header_version_map.tsv` + `drop_blocks.py`

**Files:**
- Create: `Maintenance/itk5to6/lib/header_version_map.tsv`
- Create: `Maintenance/itk5to6/lib/drop_blocks.py`
- Test: `Maintenance/itk5to6/tests/test_drop_blocks.py`

**Interfaces:**
- Produces (Python module + CLI):
  - `drop_blocks.py --floor-major N [--floor-minor M] [--apply] [--map TSV] FILE...`
  - For each file, parses `#if/#ifdef/#elif/#else/#endif` regions. Resolves a region's condition to `KEEP`/`DROP`/`AMBIGUOUS` when it is:
    - `ITK_VERSION_MAJOR <op> K` (and optional `&& ITK_VERSION_MINOR <op> M`) — arithmetic vs floor.
    - `defined(ITK_*)` / `__has_include(<itkX.h>)` where the header appears in the map with a first-version ≤ floor → the include is always true at the floor → `KEEP` that branch, `DROP` the `#else`.
  - Prints an annotated report; with `--apply`, rewrites only files whose every touched region is unambiguous (KEEP branch retained, DROP branch + directives removed).
  - Exit: `0` applied/clean, `2` ambiguous regions present, `1` parse error.

- [ ] **Step 1: Write failing pytest-free test** (plain python asserts run via `python3`)

Create `Maintenance/itk5to6/tests/test_drop_blocks.py`:

```python
import subprocess, sys, tempfile, os, textwrap
DB = os.path.join(os.environ.get("TOOLKIT", os.path.dirname(__file__)+"/.."), "lib", "drop_blocks.py")

def run(src, *args):
    d = tempfile.mkdtemp(); p = os.path.join(d, "f.cxx")
    open(p, "w").write(textwrap.dedent(src))
    r = subprocess.run([sys.executable, DB, *args, p], capture_output=True, text=True)
    return open(p).read(), r.returncode, r.stdout

def test_drop_v6_floor_keeps_ge6():
    src = """\
    #if ITK_VERSION_MAJOR >= 6
    new_api();
    #else
    old_api();
    #endif
    """
    out, rc, _ = run(src, "--floor-major", "6", "--apply")
    assert "new_api();" in out
    assert "old_api();" not in out
    assert "#if" not in out and "#endif" not in out
    assert rc == 0

def test_ambiguous_left_intact():
    src = "#if SOME_UNKNOWN_MACRO\nx();\n#else\ny();\n#endif\n"
    out, rc, _ = run(src, "--floor-major", "6", "--apply")
    assert "#if SOME_UNKNOWN_MACRO" in out      # untouched
    assert rc == 2

def test_has_include_at_floor():
    src = '#if __has_include(<itkMatrixExponential.h>)\nhave();\n#else\nlack();\n#endif\n'
    out, rc, _ = run(src, "--floor-major", "6", "--apply",
                     "--map", os.path.join(os.path.dirname(DB), "header_version_map.tsv"))
    assert "have();" in out and "lack();" not in out

if __name__ == "__main__":
    test_drop_v6_floor_keeps_ge6(); test_ambiguous_left_intact(); test_has_include_at_floor()
    print("PASS test_drop_blocks")
```

- [ ] **Step 2: Run to verify failure**

Run: `TOOLKIT=Maintenance/itk5to6 python3 Maintenance/itk5to6/tests/test_drop_blocks.py`
Expected: FAIL — `drop_blocks.py` missing.

- [ ] **Step 3: Create `header_version_map.tsv`** (seed with known headers; one `<header>\t<first-version>` per line):

```
itkMatrixExponential.h	5.0
itkOptimizerParameters.h	5.0
itkMultiThreaderBase.h	5.0
```

- [ ] **Step 4: Implement `drop_blocks.py`** — a single-pass scanner that:
  1. Tokenizes lines into directive vs body; tracks nesting with a stack of regions.
  2. Evaluates a condition string with three resolvers (version-arithmetic, `defined()`, `__has_include`); returns `True`/`False`/`None`(ambiguous).
  3. On `--apply` and a fully-resolvable `#if/#else/#endif` (no `#elif` chains it can't fold), emits only the kept branch's body and discards directives; otherwise copies the region verbatim and marks the file ambiguous.
  4. Prints `path:line  KEEP <cond> / DROP <else> / AMBIGUOUS <cond>`.

(The worker writes the parser in full; it is ~150 lines. Keep `#elif` chains: resolve top-down, keep the first True branch, drop the rest only if all conditions resolve; else AMBIGUOUS.)

- [ ] **Step 5: Run tests to verify pass**

Run: `TOOLKIT=Maintenance/itk5to6 python3 Maintenance/itk5to6/tests/test_drop_blocks.py`
Expected: `PASS test_drop_blocks`

- [ ] **Step 6: Commit**

```bash
git add Maintenance/itk5to6/lib/drop_blocks.py Maintenance/itk5to6/lib/header_version_map.tsv Maintenance/itk5to6/tests/test_drop_blocks.py
git commit -m "ENH: itk5to6 preprocessor block resolver and header-version map for drop scripts"
```

---

## Task 9: Drop scripts `drop-itk-v5.sh` / `drop-itk-before-v5.sh`

**Files:**
- Create: `Maintenance/itk5to6/drop/drop-itk-v5.sh`
- Create: `Maintenance/itk5to6/drop/drop-itk-before-v5.sh`
- Test: `Maintenance/itk5to6/tests/test_drop_scripts.sh`

**Interfaces:**
- Consumes: `lib/migrate_common.sh` (discovery, branch guard), `lib/drop_blocks.py`.
- Produces: two CLIs. Default `--dry-run`; `--apply` required to edit. `drop-itk-v5` passes `--floor-major 6`; `drop-itk-before-v5` passes `--floor-major 5`. Both restrict discovery to C/C++ sources containing `ITK_VERSION_MAJOR`, `__has_include`, or mapped headers, excluding `ThirdParty/`. They stage edited files; emit a commit message; never commit.

- [ ] **Step 1: Failing test**

```bash
#!/usr/bin/env bash
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
repo="$(mk_fixture_repo)"; cd "$repo"
cat > a.cxx <<'EOF'
#if ITK_VERSION_MAJOR >= 6
new_api();
#else
old_api();
#endif
EOF
git add a.cxx >/dev/null
# default dry-run leaves file unchanged
bash "$TOOLKIT/drop/drop-itk-v5.sh" "$repo" >/dev/null
assert_file_contains a.cxx old_api
# --apply removes the < v6 branch
bash "$TOOLKIT/drop/drop-itk-v5.sh" --apply "$repo" >/dev/null
assert_file_contains a.cxx new_api
assert_file_not_contains a.cxx old_api
assert_staged a.cxx
echo "PASS test_drop_scripts"
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Implement `drop-itk-v5.sh`**

```bash
#!/usr/bin/env bash
set -uo pipefail
LIBDIR="$(cd "$(dirname "$0")/../lib" && pwd)"
source "$LIBDIR/migrate_common.sh"
TASK_NAME="drop-itk-v5"
MC_DRY_RUN=1   # default dry-run for drop scripts
mc_init "$@"   # may flip to apply via --apply
mc_branch_guard || exit 1
mapfile -t files < <(git grep -lE -- 'ITK_VERSION_MAJOR|__has_include' 2>/dev/null | grep -vE '(^|/)ThirdParty/' || true)
[ "${#files[@]}" -gt 0 ] || { echo "[drop-itk-v5] nothing to do"; exit 0; }
applyflag=(); [ "$MC_DRY_RUN" -eq 0 ] && applyflag=(--apply)
python3 "$LIBDIR/drop_blocks.py" --floor-major 6 --map "$LIBDIR/header_version_map.tsv" "${applyflag[@]}" "${files[@]}"
rc=$?
if [ "$MC_DRY_RUN" -eq 0 ] && [ "$rc" -ne 1 ]; then
  mc_stage "${files[@]}"
  COMMIT_MSG="ENH: Drop pre-ITKv6 compatibility branches

Removes #if ITK_VERSION_MAJOR < 6 (and equivalent __has_include) dead
branches now that the build floor is ITKv6.1. Ambiguous blocks were left
intact and reported for manual review."
  mc_emit_commit_message "$TASK_NAME"
fi
exit "$rc"
```

- [ ] **Step 4: Implement `drop-itk-before-v5.sh`** — identical except `TASK_NAME="drop-itk-before-v5"`, `--floor-major 5`, and the commit message references ITKv4 branches / `ITKV4_COMPATIBILITY`.

- [ ] **Step 5: Run tests** → `PASS test_drop_scripts`.

- [ ] **Step 6: Commit**

```bash
git add Maintenance/itk5to6/drop Maintenance/itk5to6/tests/test_drop_scripts.sh
git commit -m "ENH: itk5to6 drop-itk-v5 and drop-itk-before-v5 version-guard pruners"
```

---

## Task 10: Manual / assisted scripts

**Files:**
- Create each under `Maintenance/itk5to6/manual/`: `threaded-generate-data.sh`, `multithreader-backends.sh`, `barrier-to-parallelize.sh`, `mutex-atomic-to-std.sh`, `stl-replacements.sh`, `spatialobject-space.sh`, `verify-const-qualifier.sh`, `python-cleanups.sh`, `vtk-version-bump.sh`, `cmake-cxx-floor.sh`
- Test: `Maintenance/itk5to6/tests/test_manual.sh`

**Interfaces:**
- Consumes: `lib/migrate_common.sh`.
- Produces: assisted scripts. Each applies the *safe* renames via `run_regex_review_task` (so pure renames like `SetNumberOfThreads`→`SetNumberOfWorkUnits`, `AddSpatialObject`→`AddChild`, `GetObjects`→`GetChildren`, `Dimension`→`ObjectDimension` are mechanized) and then prints a structured guidance block for the judgment parts, returning 2 when manual follow-up is required.

**Safe-rename tables (applied) per script:**
- `multithreader-backends.sh`: `s/SetNumberOfThreads/SetNumberOfWorkUnits/g`, `s/GetNumberOfThreads/GetNumberOfWorkUnits/g`, `s/ThreadInfoStruct/WorkUnitInfo/g`; **guidance:** choosing PlatformMultiThreader vs PoolMultiThreader; `ThreadedGenerateData`→`DynamicThreadedGenerateData` requires removing `threadId` use.
- `mutex-atomic-to-std.sh`: `s/itk::SimpleFastMutexLock/std::mutex/g`, `.../FastMutexLock/std::mutex/`, `s/itk::AtomicInt<\(.*\)>/std::atomic<\1>/g`; **guidance:** replace `#include "itkSimpleFastMutexLock.h"` with `<mutex>`/`<atomic>` (printed list).
- `stl-replacements.sh`: `s/itksys::hash_map/std::unordered_map/g`, `s/mpl::EnableIf/std::enable_if_t/g`, etc.; **guidance:** include changes; `find()` semantics differ for hash_map.
- `spatialobject-space.sh`: applies the LOW-risk renames listed above; **guidance:** every `IsInside(` must become `IsInsideInObjectSpace(`/`IsInsideInWorldSpace(` per call-site space — printed as a review list, never auto-renamed.
- `verify-const-qualifier.sh`: report-only — find overrides of `VerifyPreconditions`/`VerifyInputInformation` lacking `const`.
- `python-cleanups.sh`: report `itkConfig.LazyLoading`, `long double` wrapping, numpy `.T` assumptions.
- `vtk-version-bump.sh`: `MC_FILE_GLOB='*.cmake CMakeLists.txt'`; `s/find_package(VTK 8[.0-9]*/find_package(VTK 9.1/`; guidance about distribution availability.
- `cmake-cxx-floor.sh`: detect `CMAKE_CXX_STANDARD` < 17 and CMake `cmake_minimum_required` below the ITK floor; **report + suggest** only (per spec §8 these are not required fixes; trivial fixes allowed). Warn about inter-project implications.
- `barrier-to-parallelize.sh`, `threaded-generate-data.sh`: report-only (too structural for regex), printing the migration-guide recipe.

- [ ] **Step 1: Failing test** (assert the safe renames happen and report-only scripts exit 2)

```bash
#!/usr/bin/env bash
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
M="$TOOLKIT/manual"
repo="$(mk_fixture_repo)"; cd "$repo"
printf 'filter->SetNumberOfThreads(4); auto s=ThreadInfoStruct{};\n' > a.cxx
printf 'so->AddSpatialObject(c); so->GetObjects();\n' > b.cxx
git add . >/dev/null
bash "$M/multithreader-backends.sh" "$repo" >/dev/null || true
bash "$M/spatialobject-space.sh" "$repo" >/dev/null || true
assert_file_contains a.cxx SetNumberOfWorkUnits
assert_file_contains a.cxx WorkUnitInfo
assert_file_contains b.cxx AddChild
assert_file_contains b.cxx GetChildren
echo "PASS test_manual"
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Implement the 10 scripts** per the tables above. Report-only scripts set no `SED_EXPRS` and call a new helper `mc_report_only` (add to lib: prints matched `file:line` with an inline guidance string and returns 2). Add `mc_report_only` to `lib/migrate_common.sh`:

```bash
mc_report_only() {  # $1 = guidance string; uses GREP_PATTERN
  local hits; hits="$(git grep -nE -- "$GREP_PATTERN" 2>/dev/null | grep -vE '(^|/)ThirdParty/' || true)"
  [ -n "$hits" ] || { printf '[%s] nothing to do\n' "$TASK_NAME"; return 0; }
  printf '[%s] manual review required:\n%s\n\nGUIDANCE: %s\n' "$TASK_NAME" "$hits" "$1"
  return 2
}
```

- [ ] **Step 4: Run tests** → `PASS test_manual`.

- [ ] **Step 5: Commit**

```bash
git add Maintenance/itk5to6/manual Maintenance/itk5to6/lib/migrate_common.sh Maintenance/itk5to6/tests/test_manual.sh
git commit -m "ENH: itk5to6 manual/assisted tasks (threading, mutex, STL, SpatialObject, VTK, CMake/C++ floor)"
```

---

## Task 11: Agent-skill wrappers

**Files:**
- Create: `Maintenance/itk5to6/skills/itk-migrate-v6/SKILL.md`
- Create: `Maintenance/itk5to6/skills/itk-drop-version/SKILL.md`
- Test: `Maintenance/itk5to6/tests/test_skills.sh`

**Interfaces:**
- Produces: two SKILL.md files with v2 frontmatter (per `skill-framework.md`): `name`, `version`, `purpose`, `description`, `triggers`, `user_invocable`, `cmd`, `argument_hint`, `contract.*`, `dependencies.*`, `deployment.*`. `name` values: `itk-migrate-v6`, `itk-drop-version` (hyphenated, valid `<scope>-<verb>`). `contract.side_effects.user_confirmation_required: true`, `network_required: false`, `git_required: true`, `modifies_working_tree: true`. `determinism: hybrid`.

- [ ] **Step 1: Failing test** (frontmatter sanity)

```bash
#!/usr/bin/env bash
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
for s in itk-migrate-v6 itk-drop-version; do
  f="$TOOLKIT/skills/$s/SKILL.md"
  assert_file_contains "$f" "name: $s"
  assert_file_contains "$f" "user_invocable"
  assert_file_contains "$f" "user_confirmation_required"
done
echo "PASS test_skills"
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Write `itk-migrate-v6/SKILL.md`** — body instructs: detect repo + branch (offer branch creation per branch guard), run `itk-migrate.sh status`, then drive `level mandatory` → build-check → `level legacy-remove` (only if user opts into `ITK_LEGACY_REMOVE`) → `level future-legacy-remove` (only if user opts into `ITK_FUTURE_LEGACY_REMOVE`), one task at a time; for `manual/*` scripts, apply Claude judgment to the printed guidance; after each task, surface the suggested commit message and STOP for the human to validate (pre-commit) and commit; never open a PR (cite `pr-no-unsolicited.md`). Include trigger phrases ("migrate to ITK v6", "itk5to6", "apply ITK_LEGACY_REMOVE migration").

- [ ] **Step 4: Write `itk-drop-version/SKILL.md`** — body: run the appropriate drop script in default dry-run, present the KEEP/DROP/AMBIGUOUS report, resolve `AMBIGUOUS` blocks with Claude judgment (editing by hand where the script cannot), then re-run with `--apply`, stage, surface commit message, STOP. Triggers: "drop ITKv5 support", "drop ITKv4 support", "remove version guards".

- [ ] **Step 5: Run tests** → `PASS test_skills`.

- [ ] **Step 6: Commit**

```bash
git add Maintenance/itk5to6/skills Maintenance/itk5to6/tests/test_skills.sh
git commit -m "ENH: itk5to6 agent-skill wrappers (itk-migrate-v6, itk-drop-version)"
```

---

## Task 12: README + end-to-end integration test

**Files:**
- Create: `Maintenance/itk5to6/README.md`
- Test: `Maintenance/itk5to6/tests/test_integration.sh`

**Interfaces:** Consumes everything; produces user-facing docs and a full-funnel smoke test.

- [ ] **Step 1: Write the integration test** — build a fixture repo containing one of every pattern, run `prep-v5` → `mandatory` → `legacy-remove` → `future-legacy-remove` via the driver, then `drop-itk-v5 --apply`, and assert the final file is fully modernized and free of every old token.

```bash
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
git add big.cxx >/dev/null
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
```

- [ ] **Step 2: Run it; fix any task interaction bugs surfaced** (e.g. ordering, glob filters). Expected once green: `PASS test_integration`.

- [ ] **Step 3: Write `README.md`** — funnel diagram (copy spec §2), the level model table (spec §3), usage (`itk-migrate.sh` subcommands), the drop-script floors + dry-run-default safety note, the branch-guard behavior, the "human reviews/validates/commits; no PRs" contract, and a note that this supersedes `migrate-itk6-code-recommendations.sh` when upstreamed.

- [ ] **Step 4: Run the entire suite**

Run: `bash Maintenance/itk5to6/tests/run_tests.sh`
Expected: all tests `passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add Maintenance/itk5to6/README.md Maintenance/itk5to6/tests/test_integration.sh
git commit -m "DOC: itk5to6 README and end-to-end migration integration test"
```

---

## Self-Review

**Spec coverage:**
- §1 purpose, one-task, suggested-commit-msg, no-PR → Tasks 2,3,4–7,10 (commit msgs), global constraints ✓
- §1 incorporate all of `migrate-itk6-code-recommendations.sh` → Tasks 6 (TypeMacro/DISALLOW/StaticConst), 7 (CoordRep), 5 (ITKv5_CONST) cover all 5 of its transforms ✓
- §1 funnel through v5.4.6 + prep-v5 support → Task 4 ✓
- §1/§9 branch prompt on main/master → Task 2 `mc_branch_guard` ✓
- §2 funnel model, two axes → Tasks 4–7 (convert) + Task 9 (drop) ✓
- §3 levels L1/L2/L3 + prep-v5 → Tasks 4,5,6,7 ✓
- §4 directory layout → all tasks create exactly those paths ✓
- §4 `header_version_map.tsv`, branch-guard in lib → Task 8, Task 2 ✓
- §5 per-task contract (discovery/modes/idempotency/msg/no-git/reporting/exit codes) → Task 2 lib ✓
- §5.1 sed-able / regex-with-review / assisted → Tasks 4 (sed), 6 (regex-review), 10 (assisted) ✓
- §6 drop precedence (feature/`__has_include` → defines → version arithmetic), dry-run default, ambiguous-intact → Tasks 8,9 ✓
- §6 `__has_include` ↔ version map (itkMatrixExponential.h) → Task 8 ✓
- §7 driver list/status/run/level + build-check → Task 3 ✓
- §8 skills ship in PR, v2 frontmatter → Task 11 ✓
- §8 CMake-to-min-ITK floor + C++17 floor (warn, not required) → Task 10 `cmake-cxx-floor.sh` ✓
- §9 safety non-negotiables → Tasks 2,8,9 + global constraints ✓
- §10 out of scope (no PRs, consumers-only, no full CPP expansion, not perfect) → respected throughout ✓

**Placeholder scan:** the `30-cmake-lowercase.sh`, `40-itkdeprecated-classes.sh`, several `manual/*` and the `drop_blocks.py` parser body are described by behavior + exact sed tables rather than full source, because they are mechanical given the tables and verbatim regexes provided; the implementer has the exact transforms and commit-message text. No `TBD`/`TODO` left.

**Type/name consistency:** library functions (`mc_init`, `mc_files_with`, `mc_apply_sed`, `mc_stage`, `mc_branch_guard`, `mc_emit_commit_message`, `mc_report_only`, `run_text_substitution_task`, `run_regex_review_task`) are defined in Task 2/10 and used consistently in Tasks 3–10. Globals (`TASK_NAME`, `TASK_LEVEL`, `GREP_PATTERN`, `SED_EXPRS`, `RESIDUAL_PATTERN`, `COMMIT_MSG`, `MC_FILE_GLOB`, `MC_DRY_RUN`, `MC_STAGE`, `MC_META_ONLY`) are named identically everywhere. `drop_blocks.py` CLI flags (`--floor-major`, `--floor-minor`, `--apply`, `--map`) match between Tasks 8 and 9.
