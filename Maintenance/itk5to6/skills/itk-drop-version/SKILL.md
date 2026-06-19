---
name: itk-drop-version
version: 0.1.0
purpose: Remove version-guard CPP blocks for a chosen ITK floor version from a downstream consumer.
description: Runs the appropriate drop script dry-run first, resolves AMBIGUOUS blocks with Claude judgment, then re-runs with --apply; stages changes and surfaces a commit message for human review.
triggers:
  - drop ITKv5 support
  - drop ITKv4 support
  - remove version guards
  - remove ITK version ifdefs
  - drop ITK before v5 support
  - clean up ITK version guards
  - apply drop-itk-v5
  - apply drop-itk-before-v5
user_invocable: true
cmd: "bash Maintenance/itk5to6/drop/drop-itk-v5.sh"
argument_hint: "[--apply] [path]  # default is dry-run; use drop-itk-before-v5.sh for floor=5"

contract:
  inputs: Consumer repo working tree path (default = current directory) and the desired floor version (6 for v6-floor, 5 for v5-floor).
  outputs: Modified source files staged in git index, with a suggested commit message printed to stdout.
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths: ["<consumer-repo working tree> — source and header files with version guards removed"]
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
    - Maintenance/itk5to6/drop/drop-itk-v5.sh
    - Maintenance/itk5to6/drop/drop-itk-before-v5.sh

deployment:
  tier: project
  target_projects:
    - ITK downstream consumers (ANTs, BRAINSTools, elastix, SimpleITK, c3d, MITK, Slicer, ITK remote modules)
  needs_loader_dir: false
  adapters:
    - claude-code
---

# itk-drop-version

Agent skill for removing ITK version-guard CPP blocks (`#if ITK_VERSION_MAJOR >= N` / `#if defined(ITK_VERSION_GE_...)` etc.) from a downstream consumer repository.

## Overview

Two drop scripts are available:
- `drop/drop-itk-v5.sh` — floor = 6 (keep only v6+ code paths, drop v5 guards)
- `drop/drop-itk-before-v5.sh` — floor = 5 (keep only v5+ code paths, drop pre-v5 guards)

Both default to **dry-run**. Pass `--apply` only after reviewing the report.

## Workflow

### 1. Choose the right script

Ask the user: "What is the minimum ITK version your consumer will support going forward — v5 or v6?"

- **v6 floor** → use `drop-itk-v5.sh`
- **v5 floor** → use `drop-itk-before-v5.sh`

### 2. Dry-run pass

```bash
bash Maintenance/itk5to6/drop/drop-itk-v5.sh [path]
```

(Omit `--apply` — default is dry-run.)

Capture and present the full report. The script classifies blocks as:
- `KEEP` — code path for the new floor; the guard is removed, body kept.
- `DROP` — obsolete code path; entire block removed.
- `DROP_ALL` — entire `#if/#elif/#else/#endif` ladder removed.
- `AMBIGUOUS` — the script cannot determine which branch to keep.

### 3. Resolve AMBIGUOUS blocks

For each `AMBIGUOUS` block:
- Display the surrounding context (the full `#if … #endif` ladder).
- Apply Claude judgment: inspect the version condition, the header-version map, and the feature being guarded.
- Hand-edit the file to keep the correct branch and remove the guard.
- If genuinely uncertain, pause and ask the human which branch to keep.

### 4. Apply pass

After all AMBIGUOUS blocks are resolved:

```bash
bash Maintenance/itk5to6/drop/drop-itk-v5.sh --apply [path]
```

The script applies KEEP/DROP/DROP_ALL decisions and stages the changes.

### 5. Surface and stop

Print the suggested commit message from the script's stdout. **STOP** — wait for the human to:
1. Run `pre-commit run --all-files`.
2. Review the diff.
3. Commit explicitly.

## Hard constraints

- **Never open a PR** (see `pr-no-unsolicited.md`). The human opens the PR when ready.
- **Never commit** — the script stages; the human commits.
- **Always dry-run first** — never pass `--apply` on the first invocation.
- When in doubt about an AMBIGUOUS block, ask the human rather than guessing.
