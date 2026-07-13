---
name: itk-remote-update-python-version
version: 1.0.0
purpose: Bump the minimum supported Python version for an ITK remote module across pyproject.toml (requires-python + classifiers) and any .github/workflows/*.yml files that override the reusable ITKRemoteModuleBuildTestPackageAction matrix.
description: Update the minimum Python version requirement in an ITK remote module. Changes pyproject.toml, workflow files, and optionally the reusable workflow version matrix override.
triggers:
  - itk-remote-update-python-version
  - /itk-remote-update-python-version
  - bump python version remote module
user_invocable: true
cmd: false
argument_hint: "<module-name> <min-version>"
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
      - ".github/workflows/*.yml"
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

# Update Minimum Python Version for ITK Remote Module

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-remote-update-python-version — Bump min Python version for a module

Usage:
  /itk-remote-update-python-version <module> 3.9    Set min to 3.9
  /itk-remote-update-python-version <module> 3.10   Set min to 3.10

Updates: pyproject.toml (requires-python + classifiers) and CI workflows.
```

Update the minimum supported Python version for an ITK remote module. This affects package metadata, CI build matrices, and any local workflow overrides.

## Environment

The remote-module root is resolved as:
```
${REMOTE_MODULES_DIR:-$HOME/src/REMOTE_MODULES}
```
Export `REMOTE_MODULES_DIR` if your layout differs from `~/src/REMOTE_MODULES`.

## Usage

```
/itk-remote-update-python-version <module-name> <min-version>
```

- `$0` — module name (e.g., `BioCell`, `Ultrasound`)
- `$1` — new minimum Python minor version (e.g., `10` for Python 3.10)

## Files to Update

### 1. `pyproject.toml` — Package metadata (ALWAYS)

Update the `requires-python` field:
```toml
requires-python = ">=3.<min-version>"
```

**Location:** `<module>/pyproject.toml`, typically around line 35-45.

Also check and update any Python version classifiers in the `classifiers` list if present (e.g., remove `"Programming Language :: Python :: 3.9"` entries below the new minimum).

### 2. `.github/workflows/build-test-package.yml` — CI matrix override (IF PRESENT)

Most modules inherit the Python version matrix from the reusable workflow at `InsightSoftwareConsortium/ITKRemoteModuleBuildTestPackageAction`. The default matrix is `["9","10","11"]`.

If the module passes `python3-minor-versions` as an input to the reusable workflow, update it to exclude versions below the new minimum:
```yaml
python-build-workflow:
  uses: InsightSoftwareConsortium/ITKRemoteModuleBuildTestPackageAction/...@v5.4.5
  with:
    python3-minor-versions: '["10","11"]'
```

If the module does NOT pass this input (relies on the upstream default), **no change is needed here** — the reusable workflow will still build all versions in its default matrix, but the wheel metadata from `pyproject.toml` will correctly declare the minimum.

### 3. Other workflow files with hardcoded Python versions (IF PRESENT)

Check for and update any locally-defined Python versions in:
- `test-notebooks.yml` — `python-version: '3.x'`
- `test-python-*.yml` — `python-version: 3.x`
- `build-test-package-python-cuda.yml` — `python3-minor-version` matrix
- `pre-commit.yml` — `python-version` (usually set to a specific version for tooling, may not need updating)
- `documentation.yml`, `wasm.yml` — `python-version` (usually pinned for tooling)

Only update versions that represent a **minimum** or a **build matrix**. Don't change versions pinned for specific tooling purposes (e.g., pre-commit using 3.11 regardless of package minimum).

### 4. `setup.py` / `setup.cfg` (LEGACY — rare)

These have been replaced by `pyproject.toml` in modern ITK modules. If present, update `python_requires` in `setup.py` or `setup.cfg`.

## Procedure

1. `cd "${REMOTE_MODULES_DIR:-$HOME/src/REMOTE_MODULES}/<module-name>"`
2. Read `pyproject.toml` and identify current `requires-python`
3. Search all `.github/workflows/*.yml` for Python version references
4. Update all relevant files
5. Verify no references to old minimum remain: `grep -rn "3.<old-version>" --include="*.toml" --include="*.yml" | grep -v cmake-build`
6. Report what was changed

## Commit Convention

Use the `COMP:` prefix for Python version updates:
```
COMP: Update minimum Python version to 3.<min-version>
```
