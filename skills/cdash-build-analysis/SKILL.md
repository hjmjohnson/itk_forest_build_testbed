---
name: cdash-build-analysis
version: 1.0.0
purpose: Fetch, analyze, and fix build errors and compiler warnings from CDash dashboards for any CMake/CTest project (ITK, VTK, BRAINSTools, Slicer, CTK, etc.).
description: >
  Fetch, analyze, and fix build errors and compiler warnings from CDash
  dashboards for any CMake/CTest project (ITK, VTK, BRAINSTools, Slicer,
  CTK, etc.). Auto-detects the CDash instance and project from the repo's
  CTestConfig.cmake. Use when: addressing CDash nightly failures, fixing
  compiler warnings, triaging build errors, or the user says "fix CDash
  warnings", "CDash shows errors", "nightly build failures", "check CDash",
  "what warnings are on CDash", "triage nightly builds".
  Replaces the BRAINSTools-specific fix-cdash-warnings skill.
triggers:
  - cdash-build-analysis
  - /cdash-build-analysis
user_invocable: true
cmd: false
argument_hint: "Which warnings or errors should be analyzed? (default: triage latest nightly)"
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

# CDash Build Analysis

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
cdash-build-analysis — Fetch and fix CDash build errors/warnings

Usage:
  /cdash-build-analysis                       Triage latest nightly for cwd project
  /cdash-build-analysis warnings              Focus on compiler warnings only
  /cdash-build-analysis errors                Focus on build errors only
  /cdash-build-analysis --project ITK         Override auto-detected project
  /cdash-build-analysis --build-id 12345      Analyze a specific CDash build
```

Fetch, triage, and fix build errors and compiler warnings reported on CDash
dashboards. Works with **any** CMake/CTest project that submits to CDash.

## Supported Projects

| Project | CDash Host | Project Name |
|---------|-----------|-------------|
| ITK (Insight) | `open.cdash.org` | `Insight` |
| VTK | `open.cdash.org` | `VTK` |
| BRAINSTools | `my.cdash.org` | `BRAINSTools` |
| 3D Slicer | `slicer.cdash.org` | `SlicerPreview` |
| CTK | `open.cdash.org` | `CTK` |
| Any CDash 4.x | auto-detected | auto-detected |

The CDash host and project are **auto-detected** from `CTestConfig.cmake`
in the current repository. No configuration needed.

## Available Scripts

Scripts are at `~/.claude/skills/cdash-build-analysis/scripts/`. All use
the CDash GraphQL API (no authentication required for reads).

| Script | Purpose |
|--------|---------|
| `triage_builds.py` | **Start here.** Single-command triage: lists builds, fetches warnings, deduplicates by `(sourceFile, flag)`, outputs actionable summary grouped by flag. |
| `list_builds.py` | List recent CDash builds with their warning/error counts. |
| `get_build_warnings.py` | Fetch detailed warning/error messages for a specific build ID. |
| `cdash_config.py` | Auto-detect CDash configuration from CTestConfig.cmake (also usable as a library). |

Run any script with `--help` for full usage. All support `--json` output.

## Quick Start

### Triage all nightly warnings (recommended first step)

```bash
python3 ~/.claude/skills/cdash-build-analysis/scripts/triage_builds.py
```

This auto-detects the project, lists all nightly builds with warnings,
fetches and deduplicates warnings across builds, and prints a summary
grouped by compiler flag. ThirdParty warnings are automatically excluded.

### List builds with issues

```bash
python3 ~/.claude/skills/cdash-build-analysis/scripts/list_builds.py
python3 ~/.claude/skills/cdash-build-analysis/scripts/list_builds.py --type Experimental --since 48
python3 ~/.claude/skills/cdash-build-analysis/scripts/list_builds.py --json | jq '.[] | select(.errors > 0)'
```

### Inspect a specific build

```bash
python3 ~/.claude/skills/cdash-build-analysis/scripts/get_build_warnings.py BUILD_ID
python3 ~/.claude/skills/cdash-build-analysis/scripts/get_build_warnings.py BUILD_ID --errors
python3 ~/.claude/skills/cdash-build-analysis/scripts/get_build_warnings.py BUILD_ID --json --exclude-thirdparty
```

### Override project detection

For repos without CTestConfig.cmake, or to query a different project:

```bash
python3 ~/.claude/skills/cdash-build-analysis/scripts/triage_builds.py \
  --host open.cdash.org --project Insight --project-id 2
```

## Procedure for Fixing Warnings

### 1. Identify the warnings

```bash
python3 ~/.claude/skills/cdash-build-analysis/scripts/triage_builds.py --json | \
  jq '.warnings_by_flag[] | {flag: .flag, count: .total_count, files: [.files[].sourceFile]}'
```

**Always skip:** `ThirdParty/`, `SuperBuild/`, and EP build tree paths.

If there are build **errors**, fix those first. For warnings, prioritize
the most common flag affecting the most files.

### 2. Analyze the root cause

For each warning type:
- Look up the compiler flag in GCC/Clang docs
- Read the affected source files
- Identify the **minimal** fix

**Common warning fixes:**

| Flag | Typical Fix |
|------|-------------|
| `-Wshadow` | Rename local to avoid shadowing outer scope |
| `-Wunused-parameter` | Add `(void)param;` or `[[maybe_unused]]` |
| `-Wunused-variable` | Remove or add `[[maybe_unused]]` |
| `-Wdeprecated-declarations` | Update to replacement API |
| `-Wsign-compare` | Use matching signed/unsigned types |
| `-Woverloaded-virtual` | Add `using Base::Method;` or `override` |
| `-Winconsistent-missing-override` | Add missing `override` |
| `C4805` (MSVC) | Avoid mixing `bool` and `int` |
| `C4267` (MSVC) | Add explicit `static_cast<>()` |

### 3. Create a fix branch

```bash
git fetch origin
git checkout -b fix/<warning-type>-warnings origin/main
```

### 4. Fix and verify locally

Apply minimal fixes, then build the affected targets:

```bash
cmake --build build --target <affected-target> 2>&1 | grep -c "warning:"
```

### 5. Commit and PR

Follow the project's commit format. Include:
- The exact warning message from CDash
- The compiler/OS it appeared on
- What the fix does

Open a **draft** PR. Do not convert to Ready until CI is green.

## Quality Checks

- [ ] All targeted warnings are gone in the local build
- [ ] No new warnings introduced
- [ ] Changes limited to files implicated by CDash
- [ ] Tests for affected modules pass
- [ ] Commit message references CDash build

## Architecture

```
cdash_config.py          ← auto-detects host/project from CTestConfig.cmake
    ↓
list_builds.py           ← queries CDash GraphQL for recent builds
    ↓
get_build_warnings.py    ← fetches warning details for a specific build
    ↓
triage_builds.py         ← chains list + get, deduplicates, groups by flag
```

All scripts use only Python stdlib (`urllib`, `json`, `re`, `argparse`) —
no pip dependencies required.

## Provenance

Based on [ITK PR #5923](https://github.com/InsightSoftwareConsortium/ITK/pull/5923)
by Brad Lowekamp (blowekamp), generalized for multi-project use with
auto-detection from CTestConfig.cmake.
