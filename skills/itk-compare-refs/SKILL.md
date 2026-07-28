---
name: itk-compare-refs
version: 1.0.0
purpose: Quantify what an ITK version bump changes by building two ITK trees, running both full CTest suites, and emitting one Markdown report of warning, error, and per-test status deltas.
description: >-
  Use when comparing two ITK build trees — typically the release-5.4 branch
  against the latest upstream main — to quantify what an ITK version bump
  changes: build warning deltas (new/fixed, grouped by -W flag), build errors,
  and per-test CTest status changes (regressions pass->fail, fixes fail->pass,
  new/removed/flaky tests). Builds each tree capturing the full compiler log,
  runs the full CTest suite producing structured Test.xml, and emits one
  Markdown comparison report. Keywords: ITK release-5.4 vs main, compare ITK
  refs, build warnings comparison, test regression, ctest status diff, ITK
  upgrade impact, warning/error capture.
triggers:
  - itk-compare-refs
  - /itk-compare-refs
  - compare ITK refs
  - ITK upgrade impact
  - warning delta
user_invocable: true
cmd: false
argument_hint: "[<labelA>:<buildA> <labelB>:<buildB> [outdir]]"
contract:
  inputs:
    - argument
    - env
  outputs:
    - stdout
    - file
  side_effects:
    writes_to_repo: false
    writes_to_repo_paths: []
    writes_outside_repo: true
    writes_outside_repo_paths:
      - "<outdir> (build logs, Test.xml, comparison report)"
    modifies_working_tree: false
    network_required: false
    git_required: true
    user_confirmation_required: false
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
    - cmake
    - ctest
    - ninja
    - git
  python_packages: []
  scripts:
    - compare-itk-refs.sh
    - analyze_results.py
deployment:
  tier: project
  target_projects:
    - itk
  needs_loader_dir: true
  adapters:
    - claude-code
---

# itk-compare-refs

## Overview

Compare two configured ITK build trees and report exactly how they differ in
**build warnings/errors** and **test status**. The default comparison is the
forest testbed's `release-5.4` ITK vs the latest `main` ITK, but it works for
any two CMake ITK build directories.

Core principle: **verify by artifact and structured output, not pipe exit
codes.** Builds are captured to a full log (every `warning:`/`error:` line);
tests run via `ctest -T Test` so per-test status comes from `Test.xml`, not
scraped console text.

## When to use

- Before/after pointing the forest at a new ITK `main` — quantify the blast radius.
- Auditing what an ITK release-to-main jump introduces (new `-Wdeprecated`, etc.).
- Catching **test regressions** (passed on 5.4, fails on main) and **new failures**.
- NOT for downstream consumers (ANTs/Slicer/...) — this compares ITK itself.

## Prerequisites (read first)

Both build trees must be **configured** (have `CMakeCache.txt`). For a
meaningful **test** comparison, both must be configured with
`BUILD_TESTING=ON` — the forest's `build_forest-ITK-release-5-4/ITK-build` ships
with `BUILD_TESTING:BOOL=OFF` (0 tests), so enable + rebuild tests there first:

```bash
cmake -DBUILD_TESTING=ON <release-5-4/ITK-build> && cmake --build <release-5-4/ITK-build>
```

The **warning/error** comparison works regardless of testing (just needs the
build to run). Use the same compiler/toolchain for both trees (the pixi env) so
warning sets are comparable.

## Usage

```bash
# Defaults: release-5.4 vs main from the two forests, full build + full test suite
bash skills/itk-compare-refs/compare-itk-refs.sh

# Explicit trees / labels and an output dir
bash skills/itk-compare-refs/compare-itk-refs.sh \
    release-5.4:/path/ITK-build-54  main:/path/ITK-build-main  /path/out

# Scope the test suite while iterating (regex), or skip pieces
CTEST_INCLUDE='itkMath|itkImageRegion' bash skills/itk-compare-refs/compare-itk-refs.sh
RUN_CTEST=0 bash skills/itk-compare-refs/compare-itk-refs.sh   # warnings/errors only
BUILD=0     bash skills/itk-compare-refs/compare-itk-refs.sh   # reuse build, tests only
```

| Env | Default | Meaning |
|---|---|---|
| `BUILD` | `1` | rebuild each tree to capture warnings (`0` = reuse, no warning capture) |
| `RUN_CTEST` | `1` | run the test suites (`0` = compare build only) |
| `CTEST_INCLUDE` | (all) | only run tests matching this regex (`ctest -R`) |
| `CTEST_JOBS` | ncpu/2 | parallel test jobs |
| `CTEST_TIMEOUT` | `300` | per-test timeout (seconds) |

## Output

Writes to the output dir (default `.devlocal/itk-compare-*`):
`a.buildlog`, `b.buildlog`, `a.Test.xml`, `b.Test.xml`, and **`report.md`** —
a headline (errors / regressions / net new warnings) followed by collapsed
`<details>` sections: build errors, warning deltas (grouped by `-W` flag), and
test status changes. Exit code is non-zero if the `b` (main) tree has build
errors or test regressions, so it doubles as a CI gate.

## How it works

1. For each tree: read the ITK ref (`git describe` of `CMAKE_HOME_DIRECTORY`),
   `cmake --build` to a captured log, `ctest -T Test` → copy `Testing/<tag>/Test.xml`.
2. `analyze_results.py` parses both: warnings normalized to `basename: message
   [-Wflag]` (so a warning at a shifted line still matches), tests keyed by
   name. It set-diffs warnings and joins test status across the two refs.

## Common mistakes

- **Comparing against a `BUILD_TESTING=OFF` tree** → "0 tests" with no diff.
  Enable testing and rebuild first (see Prerequisites).
- **Different toolchains** → spurious warning deltas. Build both with the pixi env.
- **Reading the pipe exit code of a `| tee` build** → masks failures; this skill
  redirects to a file and inspects the log + artifacts instead.
- **`BUILD=0` then expecting warning deltas** → no rebuild means no captured
  warnings; the warning tables will read 0/0.
```
