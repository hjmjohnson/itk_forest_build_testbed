---
name: itk-init-over-assign
version: 1.0.0
purpose: Run every initialize-over-assign stage on one forest consumer unattended and leave a local branch with one gated commit per refactor kind, plus a report and a PR body draft.
description: Master of the init-over-assign refactor. Preflights a consumer worktree in a forest (clean tree, not on main, HEAD at the catalog's upstream tip, ninja graph found, clang-tidy series matching the forest compiler), records a ctest baseline, creates branch style-init-over-assign-<YYYYMMDD>, runs eight stages over the working tree (member init, local declare-then-init, local const, container list init, container const, ITK helpers, helper constexpr, narrow scope), partitions the diff into one commit per kind with the comment check, clang-format, and the compile gate, then runs pre-commit, the full forest build, and ctest against the baseline. Writes the report and a PR body under the kit's .devlocal/. Never pushes and never opens a PR.
triggers:
  - itk-init-over-assign
  - /itk-init-over-assign
  - initialize over assign
  - init over assign across a repo
  - unattended initialization refactor
user_invocable: true
cmd: false
argument_hint: "<repo-name> [--forest <suffix>] [--stages k1,k2] [--dry-run]"
contract:
  inputs:
    - argument
  outputs:
    - stdout
    - file
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "**/*.cxx"
      - "**/*.h"
      - "**/*.hxx"
      - "refs/heads/style-init-over-assign-*"
    writes_outside_repo: true
    writes_outside_repo_paths:
      - "<kit>/.devlocal/init-over-assign/"
      - "<kit>/.devlocal/pr-bodies/<repo>-init-over-assign.md"
    modifies_working_tree: true
    network_required: true
    git_required: true
    user_confirmation_required: false
  determinism: deterministic
  cache:
    has_cache: true
    cache_root: "<kit>/.devlocal/init-over-assign/baselines"
    schema_version: 1
    rebuildable: true
  derivation:
    has_ai_derived_layer: false
    derivation_version: 0
dependencies:
  skills:
    - itk-member-init
    - itk-declare-then-init
    - itk-const-promote
    - itk-container-list-init
    - itk-sizetype-filled
    - itk-allocate-initialized
    - itk-mechanical-cleanup
    - itk-narrow-scope
  external_tools:
    - git
    - pixi
    - clang-tidy
    - clang-query
    - clang-apply-replacements
    - clang-format
    - pre-commit
    - ninja
    - ctest
  python_packages: []
  scripts:
    - run.py
    - lib/ioa/pipeline.py
    - lib/ioa/report.py
    - lib/ioa/partition.py
    - lib/ioa/preflight.py
    - lib/ioa/baseline.py
    - lib/ioa/stages.py
    - lib/ioa/manifest.py
    - lib/ioa/skip.py
deployment:
  tier: project
  target_projects:
    - itk
    - brainstools
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK Init Over Assign (master)

## Quick reference

If invoked without arguments, print this and ask which consumer to run:

```
itk-init-over-assign: one unattended run, one local branch, one commit per kind

Usage (from the kit root, under pixi):
  pixi run python skills/itk-init-over-assign/run.py <repo> [options]

  <repo>        consumer directory in the forest, e.g. BRAINSTools
  --forest S    forest suffix; the forest is build_forest-S (default itk-main)
  --stages K    comma-separated kinds to run; a const kind needs its parent
  --dry-run     preflight and branch check, then print every stage,
                pre-commit, build, and ctest command and stop

Exit:  0 green   1 failing stage, raised step, pre-commit failure, build
                   error, ctest not run, or new ctest failure
       2 refusal: preflight, existing branch, or baseline (no branch made)
Out:   <kit>/.devlocal/init-over-assign/<repo>-<YYYYMMDD_HHMM>.md
       <kit>/.devlocal/pr-bodies/<repo>-init-over-assign.md
```

The first line printed is the coordinate line, so every log names what it
ran against:

```
Repo: BRAINSTools (0123456789ab) | Forest: build_forest-itk-main | ITK: 6.0.0
```

For a supervised, one-class-at-a-time loop with a human between commits,
use `itk-incremental-refactor-loop` instead.

## Stages

Each stage edits the working tree only; nothing is committed until all of
them have run. A const stage runs `itk-const-promote` with `--only-from`
set to the preceding stage's manifest, so it promotes only sites that stage
produced.

| # | Kind | Runs |
|---|------|------|
| 1 | `member-init` | `itk-member-init/member_init.py` |
| 2 | `local-init` | `itk-declare-then-init` with seven classes |
| 2c | `local-const` | `itk-const-promote --kind local-const` |
| 3 | `container-list-init` | `itk-container-list-init/list_init.py` |
| 3c | `container-const` | `itk-const-promote --kind container-const` |
| 4 | `itk-helpers` | four helpers, one merged manifest |
| 4c | `itk-helpers-constexpr` | `itk-const-promote` |
| 5 | `narrow-scope` | `itk-narrow-scope/narrow_scope.py` |

Stage 2 passes `--classes assign,elem_diff,elem_zero,sized_ctor,
stream_open,bool_branch,placeholder` (one argument, no spaces). Stage 4 runs
`itk-sizetype-filled`, `itk-allocate-initialized`, and the
`in-class-member-init` and `fillbuffer-over-iterate` patterns of
`itk-mechanical-cleanup` in that order. The stage list is `STAGES` in
`lib/ioa/pipeline.py`; adding a kind means adding an entry there and its
subject in `ioa.partition.SUBJECTS`.

## How a run proceeds

1. `ioa.preflight.check` refuses a dirty tree, a protected branch, a HEAD
   that is not the catalog's upstream tip, a missing ninja graph, or a
   clang-tidy series that differs from the forest compiler, with the
   codes `dirty-tree`, `on-main`, `not-at-upstream-tip`, `no-graph`, and
   `tidy-series-mismatch`. An existing `style-init-over-assign-<YYYYMMDD>`
   branch is refused as `branch-exists`. Refusals exit 2.
2. `ioa.baseline.ensure` runs ctest once per base SHA and caches it under
   `.devlocal/init-over-assign/baselines/`. A baseline that cannot run
   writes a report and exits 2 before the branch is created.
3. The branch is created from HEAD. Each stage is bracketed by
   `ioa.stages.snapshot`; manifests go to `<run>/manifests/<kind>.json` and
   the tree pairs to `<run>/snapshots.json`. A stage that exits non-zero
   stops the run with exit 1; the report names it and quotes its stderr.
4. `ioa.partition.plan` runs once over all stage records, then
   `ioa.partition.apply` commits each plan in kind order, reverting hunks
   that strand a comment or fail the compile gate.
5. `pre-commit run --all-files` is reported, never fixed: files a hook
   rewrites are listed under "pre-commit changed files (not committed)"
   and restored with `git checkout --`, so the build sees the branch tip,
   and the run exits 1. Then `pixi run build-<repo>`,
   `bin/run-matrix.sh --check-artifact`, and `--run-ctest`, each with
   `FOREST_REFERENCE_SUFFIX` set and any inherited `FOREST` or
   `BUILD_FOREST_ROOT` removed. A failures token without
   `LastTestsFailed.log`, a run that did not execute, or a new failure
   against the baseline exits 1.
6. Any exception after the stages still writes the report, with the step,
   the exception, and its last frame under "Run error", and exits 1.

The run never pushes, never calls `gh`, and writes into the consumer only
through the stage scripts and the partitioner.

## Report

One row per commit (SHA, kind, files, sites, gate result), the commits that
share no file with any other (candidates for separate PRs), the skip list
grouped by reason with `file:line`, pre-commit, build, and ctest results
with the warnings in the rebuild log quoted, notes such as a stage that
wrote no manifest, and a failing-stage or run-error section when the run
stopped early. The PR body draft follows `pr-message-format`: a short
summary, `<details>` for what changed and for testing with the AI
disclosure, and an HTML comment with the kit commit, run directory, and
baseline file.

## Tests

```bash
PYTHONPATH=skills/itk-init-over-assign/lib pixi run pytest skills/itk-init-over-assign/tests -v
```

`tests/test_run.py` fakes preflight, the baseline, snapshots, the
partitioner, and every subprocess, and checks stage order, the
`--only-from` wiring, exit codes, a single plan after all stages, the
report sections, and that no command pushes or calls `gh`.
