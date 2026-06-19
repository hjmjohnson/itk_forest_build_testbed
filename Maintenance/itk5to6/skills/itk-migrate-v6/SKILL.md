---
name: itk-migrate-v6
version: 0.1.0
purpose: Drive incremental ITK v5→v6 API migration in a downstream consumer repository.
description: Runs itk-migrate.sh level-by-level (mandatory → legacy-remove → future-legacy-remove), one task at a time, stopping after each for human validation and commit.
triggers:
  - migrate to ITK v6
  - itk5to6 migration
  - apply ITK v6 migration
  - apply ITK_LEGACY_REMOVE migration
  - apply ITK_FUTURE_LEGACY_REMOVE migration
  - run itk-migrate
  - upgrade downstream to ITK v6
user_invocable: true
cmd: "bash Maintenance/itk5to6/itk-migrate.sh"
argument_hint: "[status | run <task> | level <L>] [--dry-run] [path]"

contract:
  inputs: Consumer repo working tree path (default = current directory).
  outputs: Modified source files staged in git index, with a suggested commit message printed to stdout.
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths: ["<consumer-repo working tree> — modified source and header files"]
    writes_outside_repo: false
    modifies_working_tree: true
    network_required: false
    git_required: true
    user_confirmation_required: true
  determinism: hybrid
  cache:
    has_cache: false
    cache_root: ""
    schema_version: 1
    rebuildable: true
  derivation:
    has_ai_derived_layer: false
    derivation_version: 1

dependencies:
  skills: []
  external_tools:
    - git
    - python3
    - sed
    - gsed
  python_packages: []
  scripts:
    - Maintenance/itk5to6/itk-migrate.sh
    - Maintenance/itk5to6/tasks/mandatory/
    - Maintenance/itk5to6/tasks/legacy-remove/
    - Maintenance/itk5to6/tasks/future-legacy-remove/
    - Maintenance/itk5to6/tasks/prep-v5/
    - Maintenance/itk5to6/manual/

deployment:
  tier: project
  target_projects:
    - ITK downstream consumers (ANTs, BRAINSTools, elastix, SimpleITK, c3d, MITK, Slicer, ITK remote modules)
  needs_loader_dir: false
  adapters:
    - claude-code
---

# itk-migrate-v6

Agent skill for driving an incremental ITK v5→v6 API migration in any downstream consumer repository.

## Overview

This skill wraps `Maintenance/itk5to6/itk-migrate.sh`. It never commits, branches, or opens a PR — after each task the agent surfaces the suggested commit message and stops so the human can validate (run `pre-commit`), then commit.

## Workflow

### 0. Branch guard

Detect the current branch. If the working tree is on `main` or `master`, **offer** to create a working branch — do NOT create it silently. Wait for explicit human confirmation before proceeding.

### 1. Status survey

```bash
bash Maintenance/itk5to6/itk-migrate.sh status [path]
```

Present the full PENDING / DONE / SKIP table. Note if the consumer repo is coming from an ITK release older than v5.4.6 — if so, the `prep-v5` level must be completed first before `mandatory`.

### 2. Level mandatory (always required)

Iterate through each pending task in `level mandatory` **one task at a time**:

```bash
bash Maintenance/itk5to6/itk-migrate.sh run <task> [path]          # apply + stage
bash Maintenance/itk5to6/itk-migrate.sh run <task> --dry-run [path] # preview first
```

After each task:
- Print the suggested commit message from the script's stdout.
- Run a build check if the human has provided a build command (e.g. `cmake --build build -j8`), honoring the `pr-local-test-first.md` rule.
- **STOP** — wait for human to run `pre-commit run --all-files`, review, and commit.
- Only proceed to the next task after explicit human go-ahead.

### 3. Level legacy-remove (opt-in only)

Ask the user: "Do you want to apply `ITK_LEGACY_REMOVE` migrations? (This removes backward-compat shims that ITK may drop in a future release.)"

Only if the user explicitly answers yes:

```bash
bash Maintenance/itk5to6/itk-migrate.sh level legacy-remove [--build-check "cmd"] [path]
```

Still proceed one task at a time, stopping after each for human validation.

### 4. Level future-legacy-remove (opt-in only)

Ask the user: "Do you want to apply `ITK_FUTURE_LEGACY_REMOVE` migrations? (These prepare for APIs not yet removed but expected to be deprecated.)"

Only if the user explicitly answers yes, proceed one task at a time.

### 5. Manual / assisted scripts

Scripts under `Maintenance/itk5to6/manual/` are report-only (exit 2). When encountered:
- Run the script and display its guidance output.
- Apply Claude judgment to the printed suggestions — hand-edit source where the automated resolver cannot decide.
- Surface modified files and a suggested commit message, then stop.

## Hard constraints

- **Never open a PR** (see `pr-no-unsolicited.md`). Surface the commit message; the human commits and opens the PR when ready.
- **Never commit** — `itk-migrate.sh` stages changes; the human commits.
- **Never create a branch without explicit human confirmation.**
- Honor `pr-local-test-first.md`: build and run tests locally before declaring any task complete.
