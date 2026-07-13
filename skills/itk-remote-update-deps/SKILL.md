---
name: itk-remote-update-deps
version: 1.0.0
purpose: Relax pinned ITK sub-package version constraints in an ITK remote module's pyproject.toml from exact pins (itk-io==5.4.*) to minimums (itk-io>=5.4), enabling compatibility with both ITK 5.4.x and ITK 6.x wheels.
description: Update ITK dependency version constraints in remote modules for ITK 6 compatibility. Changes pinned versions (e.g., itk-io==5.4.*) to minimum versions (e.g., itk-io>=5.4) in pyproject.toml.
triggers:
  - itk-remote-update-deps
  - /itk-remote-update-deps
  - update ITK deps
  - relax itk pin
user_invocable: true
cmd: false
argument_hint: "<module-name|all> [--dry-run]"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "pyproject.toml"
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: true
    network_required: false
    git_required: true
    user_confirmation_required: true
  determinism: deterministic
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
  python_packages: []
  scripts: []
deployment:
  tier: project
  target_projects:
    - remote_modules
  needs_loader_dir: true
  adapters:
    - claude-code
---

# Update ITK Dependency Constraints for ITK 6

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-remote-update-deps — Relax ITK version pins for ITK 6 compat

Usage:
  /itk-remote-update-deps <module>           Update one module
  /itk-remote-update-deps all                Update all modules
  /itk-remote-update-deps <module> --dry-run Preview changes only
```

Update ITK sub-package version pins in remote module `pyproject.toml` files
from exact pins (`== 5.4.*`) to minimum version constraints (`>= 5.4`),
enabling compatibility with both ITK 5.4.x and ITK 6.x.

## Environment

The remote-module root is resolved as:
```
${REMOTE_MODULES_DIR:-$HOME/src/REMOTE_MODULES}
```
Export `REMOTE_MODULES_DIR` if your layout differs from `~/src/REMOTE_MODULES`.

## Usage

```
/itk-remote-update-deps Cuberille          # Update one module
/itk-remote-update-deps all                # Update all modules
/itk-remote-update-deps all --dry-run      # Show what would change without modifying
```

**Arguments:**
- `$0` — module name (directory under `$REMOTE_MODULES_DIR`) or `all` for every module
- `$1` — optional `--dry-run` to preview changes without writing

## Background

ITK remote modules typically pin ITK sub-package versions exactly in their
`pyproject.toml` dependencies:

```toml
dependencies = [
    "itk-io == 5.4.*",
    "numpy",
]
```

ITK 6 wheels use version `6.0.0bX`, which does not satisfy `== 5.4.*`. pip
refuses to install when the constraint conflicts. The fix is to relax the pin:

```toml
dependencies = [
    "itk-io >= 5.4",
    "numpy",
]
```

## What to change

For each module's `pyproject.toml`, find the `[project] dependencies` list
and apply these replacements:

| Pattern to find             | Replace with         |
|-----------------------------|----------------------|
| `itk-core == 5.4.*`        | `itk-core >= 5.4`   |
| `itk-filtering == 5.4.*`   | `itk-filtering >= 5.4` |
| `itk-io == 5.4.*`          | `itk-io >= 5.4`     |
| `itk-numerics == 5.4.*`    | `itk-numerics >= 5.4` |
| `itk-registration == 5.4.*`| `itk-registration >= 5.4` |
| `itk-segmentation == 5.4.*`| `itk-segmentation >= 5.4` |

More generally, any dependency matching `itk-* == 5.*` should become `itk-* >= 5.4`.
Also handle other ITK remote module cross-deps (e.g., `itk-meshtopolydata == 0.10.*`
may also need relaxing depending on context).

## Steps

1. **If `$0` is a single module name:**
   - Read `${REMOTE_MODULES_DIR:-$HOME/src/REMOTE_MODULES}/<module>/pyproject.toml`
   - Find all `itk-*` pins in the `dependencies` list
   - Replace exact pins with minimum version constraints
   - Show the diff

2. **If `$0` is `all`:**
   - Scan every subdirectory of `$REMOTE_MODULES_DIR` for `pyproject.toml`
   - Apply the same transformation to each
   - Report a summary table of modules changed vs already compatible

3. **If `--dry-run` is passed:**
   - Show what would change but do not write files

4. **After changes (unless dry-run):**
   - Ask the user if they want to commit and create PRs for the changed modules

## Commit message format

Use the ITK convention:

```
COMP: Relax ITK dependency pins for ITK 6 compatibility
```

## Notes

- Do NOT change non-ITK dependencies (numpy, etc.)
- Do NOT change build-system requires (scikit-build-core, etc.)
- Some modules may already use `>=` — skip those
- Some modules may pin other remote modules (e.g., `itk-meshtopolydata == 0.10.*`).
  Flag these for manual review rather than auto-changing.
