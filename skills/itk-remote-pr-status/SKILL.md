---
name: itk-remote-pr-status
version: 1.0.0
purpose: Show CI and review status for all open PRs authored by hjmjohnson across the ITK remote-module fleet. Emits JSON with per-PR status (ALL_PASS/PENDING/FAILING/FAIL_AND_PENDING), check counts, failed check names, review decision, assignees, and reviewers — then formats a human-readable grouped table.
description: Show CI and review status for all open ITK remote module PRs. Reports passing, pending, failing checks and review/approval state.
triggers:
  - itk-remote-pr-status
  - /itk-remote-pr-status
  - remote module PR status
user_invocable: true
cmd: false
argument_hint: "[passing|failing|pending]"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: false
    writes_to_repo_paths: []
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: false
    network_required: true
    git_required: true
    user_confirmation_required: false
  determinism: hybrid
  cache:
    has_cache: false
    cache_root:
    schema_version: 0
    rebuildable: true
  derivation:
    has_ai_derived_layer: false
    derivation_version: 0
dependencies:
  skills: []
  external_tools:
    - git
    - gh
    - python3
  python_packages: []
  scripts:
    - pr_status.py
deployment:
  tier: project
  target_projects:
    - remote_modules
  needs_loader_dir: true
  adapters:
    - claude-code
---

# PR Status for ITK Remote Modules

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-remote-pr-status — Show CI/review status for all remote module PRs

Usage:
  /itk-remote-pr-status                  Show all open PRs
  /itk-remote-pr-status passing          Show only passing PRs
  /itk-remote-pr-status failing          Show only failing PRs
  /itk-remote-pr-status pending          Show only pending PRs
```

Show the CI and review status of all open PRs authored by hjmjohnson across ITK remote modules.

## Environment

The remote-module root is resolved by `pr_status.py` via:
```
${REMOTE_MODULES_DIR:-$HOME/src/REMOTE_MODULES}
```
Export `REMOTE_MODULES_DIR` if your layout differs from `~/src/REMOTE_MODULES`.

## Usage

```
/itk-remote-pr-status              # Show all open PRs
/itk-remote-pr-status passing      # Show only fully passing PRs
/itk-remote-pr-status failing      # Show only failing PRs
/itk-remote-pr-status pending      # Show only pending PRs
```

## Implementation

Run the data collection script:

```bash
python3 ~/.claude/skills/itk-remote-pr-status/pr_status.py
```

The script outputs JSON with these fields per PR:
- `module`, `repo`, `number`, `title`, `url`, `branch`
- `status`: `ALL_PASS`, `PENDING`, `FAILING`, `FAIL_AND_PENDING`, `UNKNOWN`
- `passed`, `failed`, `pending`, `skipped`, `total` — check counts
- `failed_checks` — list of failed check names
- `review_decision` — `APPROVED`, `CHANGES_REQUESTED`, `REVIEW_REQUIRED`, or empty
- `assignees`, `reviewers` — lists of GitHub usernames

## Formatting

Present results as a table grouped by status. For each PR show:
- Module name and PR number (as a link)
- Check counts (pass/fail/pending)
- Review state (approved/pending review/changes requested)
- Assignees and reviewers

If `$ARGUMENTS` is `passing`, filter to `ALL_PASS` only.
If `$ARGUMENTS` is `failing`, filter to `FAILING` or `FAIL_AND_PENDING`.
If `$ARGUMENTS` is `pending`, filter to `PENDING`.
