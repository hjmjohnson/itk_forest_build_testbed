# ITK v5.4.6 → v6.1 Migration Toolkit

Semi-automated, one-task-at-a-time scripts (plus agent-skill wrappers) that
simplify migrating a C++/CMake/Python consumer of ITK from ITKv5.4.6 to
ITKv6.1. This toolkit supersedes `Utilities/Maintenance/migrate-itk6-code-recommendations.sh`.

## The Funnel Model

```
ITKv4 code ──[prep-v5 tasks]──▶ idiomatic on ITKv5.4.6 ──[drop-itk-before-v5]──▶ v5.4.6-floor
                                                                                      │
                                                          [migrate-v6: L1→L2→L3]──────┤
                                                                                      ▼
                                       ──[drop-itk-v5]──▶ ITKv6.1-only, no compat scaffolding
```

Two orthogonal axes:

- **Conversion tasks** modernize API usage while keeping the code compilable.
- **Drop tasks** delete dead multi-version scaffolding (`#if ITK_VERSION_MAJOR < N`
  branches, feature guards) once the consumer commits to a version floor.

If your consumer targets a release older than v5.4.6, funnel through v5.4.6
first (run `prep-v5` tasks), then proceed to the v6 migration levels.

## Instrumentation Levels

A task's level is the strictest build flag under which the *old* code stops
building:

| Level | Old code breaks when… | Representative tasks |
|---|---|---|
| **prep-v5** (pre-funnel) | n/a — makes old code idiomatic on v5.4.6 | 16 C++11-keyword macros (`ITK_NULLPTR`→`nullptr`, `ITK_OVERRIDE`→`override`, …); `atoi/atof`→`std::stoi/stod`; CMake lowercase + block-end cleanup; doxygen `\doxygen`→`\itkref` |
| **L1 mandatory** | fails against v6 **default** build | `ITKv5_CONST`→`const`; removed `ITKDeprecated` classes; `find_package(VTK 9.1)`; GoogleTest target renames; `ITK_USE_FILE` → `ITK::` targets |
| **L2 `ITK_LEGACY_REMOVE`** | builds default; fails with `ITK_LEGACY_REMOVE=ON` | `itkTypeMacro`→`itkOverrideGetNameOfClassMacro`; `itkTypeMacroNoParent`→`itkVirtualGetNameOfClassMacro`; `ITK_DISALLOW_COPY_AND_ASSIGN`→`..._MOVE`; `itkStaticConstMacro`→`static constexpr`; `itkGetStaticConstMacro`→`Self::` |
| **L3 `ITK_FUTURE_LEGACY_REMOVE`** | builds with L2 on; fails with `ITK_FUTURE_LEGACY_REMOVE=ON` | `CoordRepType`→`CoordinateType` family |

Run L1 first, then L2, then L3. `prep-v5` is the pre-funnel step for consumers
coming from a release older than v5.4.6.

## Usage: `itk-migrate.sh`

```
itk-migrate.sh list   [--level prep-v5|L1|L2|L3|manual]
itk-migrate.sh status [path]
itk-migrate.sh run    <task> [--dry-run|--no-stage] [path]
itk-migrate.sh level  <prep-v5|mandatory|legacy-remove|future-legacy-remove> \
                      [--dry-run] [--build-check "cmd"] [path]
```

### `list` — discover available tasks

```bash
# all tasks
bash itk-migrate.sh list

# only legacy-remove (L2) tasks
bash itk-migrate.sh list --level legacy-remove
```

### `status` — where am I in the funnel?

```bash
# scan the current working directory
bash itk-migrate.sh status

# scan a specific consumer repo
bash itk-migrate.sh status /path/to/my-consumer
```

Prints `PENDING` for tasks whose source pattern is still present, `clean` for
tasks already applied.

### `run` — apply one task

```bash
# dry-run (diff only, no writes)
bash itk-migrate.sh run cxx11-keyword-macros --dry-run /path/to/my-consumer

# apply and stage (default)
bash itk-migrate.sh run cxx11-keyword-macros /path/to/my-consumer

# apply without git-add
bash itk-migrate.sh run cxx11-keyword-macros --no-stage /path/to/my-consumer
```

### `level` — run all tasks at a level

```bash
# apply all mandatory (L1) tasks; stop on build failure
bash itk-migrate.sh level mandatory --build-check "cmake --build build" /path/to/my-consumer

# dry-run all legacy-remove (L2) tasks
bash itk-migrate.sh level legacy-remove --dry-run /path/to/my-consumer
```

After each task the driver prints the suggested commit message. The human
reviews, validates (`pre-commit run --all-files`), and commits. The driver
never commits or opens a PR.

## The Two Drop Scripts

Drop scripts remove dead multi-version compatibility branches. They default
to **dry-run** and emit an annotated report before touching anything.

### `drop/drop-itk-v5.sh` (floor: ITKv6.0)

Removes `#if ITK_VERSION_MAJOR < 6` branches and equivalent `__has_include`
guards. Keeps the `>= 6` branch; deletes the `< 6` branch and scaffolding.

```bash
# report what would be removed (default dry-run)
bash drop/drop-itk-v5.sh /path/to/my-consumer

# apply unambiguous blocks; leave ambiguous ones intact with a ⚠ marker
bash drop/drop-itk-v5.sh --apply /path/to/my-consumer
```

### `drop/drop-itk-before-v5.sh` (floor: ITKv5.0)

Same interface; floor is v5.0. Use this to clean up ITKv4 compatibility
scaffolding before entering the v6 funnel.

```bash
bash drop/drop-itk-before-v5.sh /path/to/my-consumer
bash drop/drop-itk-before-v5.sh --apply /path/to/my-consumer
```

### Drop-script report format

```
file.cxx:12  KEEP   #if ITK_VERSION_MAJOR >= 6  (>= 6 at floor 6 → live)
file.cxx:20  DROP   #else                        (< 6 at floor 6 → dead)
file.cxx:30  ⚠ AMBIGUOUS  (manual review required)
```

Detection precedence:
1. Feature / header guards (`__has_include`) resolved via `lib/header_version_map.tsv`.
2. Per-feature ITK defines when available.
3. Fallback: `#if ITK_VERSION_MAJOR <cmp>` arithmetic against the floor.

Only unambiguous blocks are modified by `--apply`; ambiguous blocks are left
intact and reported.

## Branch-Guard Behavior

If the target repo's current branch is `main` or `master`, every task script
prompts:

```
On branch main. [c]reate working branch / [e]dit here / [a]bort?
```

- `c` — prints the command to create a working branch, then exits (no edits).
- `e` or Enter — proceeds with edits on the current branch.
- `a` — aborts without changes.

In **non-interactive** runs (CI, pipes, test harnesses) the guard warns and
proceeds automatically so automated workflows are not blocked.

## Human Owns Git History

Each task applies the edit and stages the changed files (`git add`). The
tooling **never** commits, creates branches, or opens pull requests. After
each task:

1. Review the diff: `git diff --cached`
2. Validate: `pre-commit run --all-files`
3. Commit with the suggested message (printed to stdout and written to
   `commit-messages/<task>.msg`).

This matches `Utilities/Maintenance` conventions: the scripts accelerate the
mechanical parts; human judgment gates every commit.

## Directory Layout

```
Maintenance/itk5to6/
  README.md                       # this file
  itk-migrate.sh                  # driver
  lib/
    migrate_common.sh             # shared bash library
    header_version_map.tsv        # header → first-ITK-version map (for drop scripts)
    drop_blocks.py                # C-preprocessor-aware block parser (used by drop scripts)
  tasks/
    prep-v5/     NN-<task>.sh
    mandatory/   NN-<task>.sh
    legacy-remove/ NN-<task>.sh
    future-legacy-remove/ NN-<task>.sh
  manual/                         # assisted scripts for high-complexity items
  drop/
    drop-itk-v5.sh
    drop-itk-before-v5.sh
  commit-messages/<task>.msg      # suggested commit messages written by each task
  skills/
    itk-migrate-v6/SKILL.md       # agent-skill wrapper
    itk-drop-version/SKILL.md
  tests/
    helpers.sh
    run_tests.sh
    test_*.sh
```

## Running the Tests

```bash
bash Maintenance/itk5to6/tests/run_tests.sh
```

Expected output: `12 passed, 0 failed`.
