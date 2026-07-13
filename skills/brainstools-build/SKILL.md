---
name: brainstools-build
version: 1.0.0
purpose: Build BRAINSTools Debug and/or Release inner builds by reusing ExternalProject (EP) trees from an existing SuperBuild.
description: >-
  Build BRAINSTools Debug and/or Release inner builds by reusing ExternalProject
  (EP) trees from an existing SuperBuild. Use this skill whenever the user asks
  to build BRAINSTools, rebuild the inner project, configure a Debug or Release
  build, or run ninja on the BRAINSTools source — especially when the SuperBuild
  has already been run and only the inner code needs to be rebuilt. Also triggers
  for: "rebuild BRAINSTools", "build both debug and release", "inner build",
  "configure Release BRAINSTools", "reuse external projects", "skip superbuild".
triggers:
  - brainstools-build
  - /brainstools-build
user_invocable: true
cmd: false
argument_hint: "[debug|release|both]"
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
    network_required: false
    git_required: false
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
  external_tools: []
  python_packages: []
  scripts: []
deployment:
  tier: always
  target_projects: []
  needs_loader_dir: true
  adapters:
    - claude-code
---

# BRAINSTools Inner Build Skill

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
brainstools-build — Build BRAINSTools inner builds (reuse EP trees)

Usage:
  /brainstools-build                Build Release inner build (default)
  /brainstools-build debug          Build Debug inner build
  /brainstools-build both           Build both Debug and Release
  /brainstools-build release        Build Release inner build explicitly
```

## Background

BRAINSTools uses a **two-phase SuperBuild**:

- **Phase I (SuperBuild):** Downloads and builds all external dependencies
  (ITK, VTK, SlicerExecutionModel, TBB, zlib, ANTs) as ExternalProjects.
  These are *always* built in Release mode (`EXTERNAL_PROJECT_BUILD_TYPE=Release`).

- **Phase II (inner build):** Builds the actual BRAINSTools tools against those
  EP trees, with its own `CMAKE_BUILD_TYPE` (Debug or Release).

Both inner builds share the **same** EP trees, so after Phase I runs once,
you can configure and build Debug *and* Release inner builds with no redundant
EP compilation.

## Canonical scripts and config file

All scripts live in `Utilities/build_configs/inner/` relative to the
BRAINSTools source root:

| File | Purpose |
|------|---------|
| `BRAINSTools-modules.cmake` | CMake init-cache (`-C`) with all `USE_*` flags |
| `bt-configure-inner.sh` | Configure one inner build (Debug or Release) |
| `bt-build-both.sh` | Configure + build both Debug and Release |

## Step-by-step workflow

### 1. Verify the SuperBuild has run

Check that EP build trees exist:
```bash
ls <build_dir>/ITKv5-Release-build/  # must exist
ls <build_dir>/VTK-Release-build/    # must exist
ls <build_dir>/CMakeCache.txt        # superbuild cache
```

If they don't exist, the SuperBuild must be run first.

### 2. Configure both inner builds

```bash
cd <source_dir>
# Debug inner build
Utilities/build_configs/inner/bt-configure-inner.sh --type Debug

# Release inner build
Utilities/build_configs/inner/bt-configure-inner.sh --type Release
```

Or configure+build both in one command:
```bash
Utilities/build_configs/inner/bt-build-both.sh
```

Scripts auto-detect `SOURCE_DIR` and `BUILD_DIR` from their location.
Override with `--build-dir` / `--source-dir` or env vars
`BRAINSTOOLS_BUILD_DIR` / `BRAINSTOOLS_SOURCE_DIR`.

### 3. Build manually with ninja

```bash
# Debug
ninja -C <build_dir>/BRAINSTools-Debug-EPRelease-build -j$(( $(sysctl -n hw.logicalcpu) / 2 ))

# Release
ninja -C <build_dir>/BRAINSTools-Release-EPRelease-build -j$(( $(sysctl -n hw.logicalcpu) / 2 ))
```

### 4. Build in background (for long builds)

Use Bash `run_in_background=true` for ninja so the terminal isn't blocked.
Read the output file when the task notification arrives.

## EP path resolution

The configure script reads `CMakeCache.txt` from the SuperBuild directory
to auto-detect:

| Variable | Resolved from |
|----------|---------------|
| `ITK_DIR` | glob `ITKv5-Release-build/lib/cmake/ITK-*/` |
| `VTK_DIR` | `VTK-Release-build/` |
| `SlicerExecutionModel_DIR` | `SlicerExecutionModel-Release-build/` |
| `TBB_DIR` | `tbb-Release-build/` |
| `ANTs_SOURCE_DIR` | `ANTs/` |
| `ANTs_LIBRARY_DIR` | `<INSTALL_PREFIX>/lib` (from `CMAKE_INSTALL_PREFIX` in cache) |
| `ZLIB_ROOT` | `<INSTALL_PREFIX>` |

## Inner build directory naming

```
<build_dir>/
├── BRAINSTools-Debug-EPRelease-build/    ← Debug inner build
└── BRAINSTools-Release-EPRelease-build/  ← Release inner build
```

The `EPRelease` suffix indicates the EP build type (always Release).

## Reconfiguring

Pass `--force` to `bt-configure-inner.sh` or `bt-build-both.sh` to
re-run CMake configure even if `CMakeCache.txt` already exists:

```bash
Utilities/build_configs/inner/bt-build-both.sh --force
```

## Module selection (USE_* flags)

To add or remove tools, edit:
```
Utilities/build_configs/inner/BRAINSTools-modules.cmake
```

Then reconfigure with `--force`.

## Reporting build results

After a build, always report:
- Exit code (success/failure)
- Any first compiler error (template errors are verbose — show only the first)
- Count of linked executables for each build type
- Location of the `bin/` directory:
  `<build_dir>/BRAINSTools-<TYPE>-EPRelease-build/BRAINSTools-<TYPE>-EPRelease-build/bin/`

## Running tests and generating a report

**Always test in the Release build.** Debug is 10–20× slower and will time out
most BCD/registration tests.

```bash
cd <build_dir>/BRAINSTools-Release-EPRelease-build

# Run full suite + auto-generate report
../../Utilities/misc/BRAINSTools_run_tests.sh

# Or run tests manually then generate the report separately
ctest -j4 --timeout 6000 -O /tmp/ctest.log
../../Utilities/misc/bt-report-tests.sh /tmp/ctest.log
```

`bt-report-tests.sh` accepts:
- `[LOGFILE]`  — CTest log to parse (default: `TestResults/latest.log`)
- `-n <N>`     — show top-N slowest (default: 20)
- `-o <FILE>`  — write tab-separated raw data (num, time, status, name)

After any test run, always call `bt-report-tests.sh` and report:
- Total / Passed / Failed / Not Run counts
- Wall-clock time
- Top-20 slowest tests with times
- Full failure table (if any failures)
