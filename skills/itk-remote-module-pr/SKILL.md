---
name: itk-remote-module-pr
version: 1.0.0
purpose: Manage PRs across the ~60 ITK remote module repositories (each a separate git repo under a single parent). Supports status/diagnose/build/create/update/check-all actions, with per-module `gh repo set-default` handling and a cookbook of common CI failure patterns.
description: Manage pull requests across ITK remote modules — check CI, diagnose failures, create/update PRs, rebase, and push. Use when working with GitHub PRs on any module under REMOTE_MODULES.
triggers:
  - itk-remote-module-pr
  - /itk-remote-module-pr
  - remote module PR
user_invocable: true
cmd: false
argument_hint: "<module-name> <action> [args]"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "**"
    writes_outside_repo: true
    writes_outside_repo_paths:
      - "${REMOTE_MODULES_DIR}/*/cmake-build-release/**"
    modifies_working_tree: true
    network_required: true
    git_required: true
    user_confirmation_required: true
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
    - cmake
    - ninja
    - ctest
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

# ITK Remote Module PR Management

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-remote-module-pr — Manage PRs across ITK remote module repos

Usage:
  /itk-remote-module-pr <module> status          Show PR CI/review status
  /itk-remote-module-pr <module> diagnose         Diagnose CI failures
  /itk-remote-module-pr <module> build            Build module against ITK
  /itk-remote-module-pr <module> create           Create a new PR
  /itk-remote-module-pr <module> update           Update existing PR
  /itk-remote-module-pr check-all                 Check all module PRs
```

Manage pull requests across the ~60 ITK remote modules. Each subdirectory under the remote-modules root is a **separate git repository** for an external ITK module.

## Environment

The following environment variables control where this skill operates. Defaults assume the `~/src/` layout:

```bash
REMOTE_MODULES_DIR=${REMOTE_MODULES_DIR:-$HOME/src/REMOTE_MODULES}
ITK_SRC_DIR=${ITK_SRC_DIR:-$HOME/src/ITK}
ITK_BUILD_DIR=${ITK_BUILD_DIR:-$HOME/src/ITK/build-python}
```

Export them in your shell rc if your layout differs. All commands below assume they are set.

## Usage

```
/itk-remote-module-pr <module-name> <action> [args]
```

**Arguments:**
- `$0` — module name (directory name under `$REMOTE_MODULES_DIR`, e.g., `BioCell`, `Ultrasound`)
- `$1` — action to perform (see below)
- `$2+` — additional arguments depending on action

## Actions

| Action | Description | Example |
|--------|-------------|---------|
| `status` | Show open PRs and their CI status | `/itk-remote-module-pr BioCell status` |
| `diagnose <pr-number>` | Diagnose CI failures for a PR | `/itk-remote-module-pr BioCell diagnose 31` |
| `build` | Configure, build, and test locally | `/itk-remote-module-pr BioCell build` |
| `create <title>` | Create a new PR from current branch | `/itk-remote-module-pr BioCell create "COMP: Fix wrapping"` |
| `update <pr-number>` | Rebase on main/master and push | `/itk-remote-module-pr BioCell update 31` |
| `check-all` | Check CI status of open PRs across all modules | `/itk-remote-module-pr ALL check-all` |

## Critical Setup Steps (Every Module)

Before running any `gh` commands for a module, you MUST:

1. `cd` into the module directory
2. Determine the GitHub repository URL from the git remote
3. Run `gh repo set-default <owner/repo>` to set the correct repo context

```bash
cd "${REMOTE_MODULES_DIR:-$HOME/src/REMOTE_MODULES}/<module-name>"
GIT_REPO=$(git remote get-url origin | sed 's|.*github.com[:/]||;s|\.git$||')
gh repo set-default "$GIT_REPO"
```

## Action Details

### `status` — Show PR and CI Status

1. Navigate to module directory and set default repo
2. List open PRs: `gh pr list --state open`
3. For each PR, show CI check status: `gh pr view <number> --json title,state,statusCheckRollup`
4. Summarize: which checks pass, fail, or are pending

### `diagnose <pr-number>` — Diagnose CI Failures

1. Navigate to module directory and set default repo
2. Get PR details: `gh pr view <pr-number> --json title,headRefName,statusCheckRollup`
3. Identify failed checks from `statusCheckRollup`
4. For each failed run, get logs: `gh run view <run-id> --log-failed`
5. If logs are truncated, get specific job logs: `gh api repos/<owner>/<repo>/actions/jobs/<job-id>/logs`
6. Categorize failures:
   - **clang-format linter**: Usually Docker Hub rate limiting or actual formatting issues
   - **C++ build**: Compilation errors, missing dependencies
   - **Python build**: Wrapping issues (CastXML, SWIG), wheel build failures
   - **Infrastructure**: GitHub Actions outages, cache failures

### `build` — Local Build and Test

Configure, build, and test the module against the ITK build tree:

```bash
cd "${REMOTE_MODULES_DIR:-$HOME/src/REMOTE_MODULES}/<module-name>"

# Configure
cmake -S . -B cmake-build-release \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DBUILD_TESTING=ON \
  -DITK_DIR="${ITK_BUILD_DIR:-$HOME/src/ITK/build-python}"

# Build
ninja -C cmake-build-release

# Test
ctest --test-dir cmake-build-release
```

If wrapping is involved, check the build output for CastXML and SWIG errors. Common wrapping issues:
- **Wrong auto-include headers**: Classes in nested namespaces (e.g., `itk::bio::`, `itk::BlockMatching::`) need `set(WRAPPER_AUTO_INCLUDE_HEADERS OFF)` before `itk_wrap_include()` and `itk_wrap_class()`
- **Non-template classes**: Use `itk_wrap_simple_class()` instead of `itk_wrap_class()`/`itk_end_wrap_class()`
- **Dependency ordering**: Use `WRAPPER_SUBMODULE_ORDER` in `wrapping/CMakeLists.txt` when base classes must be processed before derived classes

### `create <title>` — Create a PR

1. Navigate to module directory and set default repo
2. Determine the default branch: `git symbolic-ref refs/remotes/origin/HEAD | sed 's|refs/remotes/origin/||'`
3. Ensure current branch is not the default branch
4. Push branch: `git push -u origin <branch-name>`
5. Create PR:
   ```bash
   gh pr create --draft \
     --title "<title>" \
     --body "$(git log origin/<default-branch>..HEAD --pretty='- %s' | head -20)" \
     --no-maintainer-edit
   ```

### `update <pr-number>` — Rebase and Push

1. Navigate to module directory and set default repo
2. Get PR branch: `gh pr view <pr-number> --json headRefName -q .headRefName`
3. Checkout the PR branch
4. Fetch and rebase: `git fetch origin <default-branch> && git rebase origin/<default-branch>`
5. If rebase conflicts, stop and report — do NOT force-resolve
6. Push: `git push origin <branch-name>` (or `--force-with-lease` if rebase rewrote history, with user confirmation)

### `check-all` — Check All Modules

Iterate over all module directories and report open PRs with failing CI:

```bash
for module_dir in "${REMOTE_MODULES_DIR:-$HOME/src/REMOTE_MODULES}"/*/; do
  [ -d "$module_dir/.git" ] || continue
  module=$(basename "$module_dir")
  # ... check for open PRs and CI status
done
```

## Conventions

- **Commit message prefixes**: `ENH:` (enhancement), `COMP:` (compilation), `STYLE:` (formatting), `BUG:` (fix), `DOC:` (documentation)
- **CI workflows**: `build-test-cxx.yml`, `build-test-package-python.yml`, `clang-format-linter.yml`
- **Reusable workflows**: Most modules reference `InsightSoftwareConsortium/ITKRemoteModuleBuildTestPackageAction@v5.4.x`
- **ITK source tree**: `${ITK_SRC_DIR:-$HOME/src/ITK}`
- **ITK build directory**: `${ITK_BUILD_DIR:-$HOME/src/ITK/build-python}`

## Common Failure Patterns

| Failure | Cause | Fix |
|---------|-------|-----|
| `ubuntu:18.04` Docker pull 401/429 | Docker Hub rate limiting EOL image | Upstream issue in ITKClangFormatLinterAction |
| `file not found` in CastXML | Wrong auto-derived header for nested namespace | `set(WRAPPER_AUTO_INCLUDE_HEADERS OFF)` |
| SWIG warning 401 "base class unknown" | Base class not wrapped or wrong ordering | `itk_wrap_simple_class` + `WRAPPER_SUBMODULE_ORDER` |
| `Cannot find file: dist/itk_*.whl` | Python wheel build failed upstream | Check "Build Python package" step logs for root cause |
| `cannot clone: Operation not permitted` | Docker-in-Docker in act | Python builds can't run locally in act |
