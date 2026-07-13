---
name: ctk-build
version: 1.0.0
purpose: Build the inner CTK project only (skips external dependencies like VTK, DCMTK).
description: Build the inner CTK project only (skips external dependencies like VTK, DCMTK). Fast for iterating on CTK source changes.
triggers:
  - ctk-build
  - /ctk-build
user_invocable: true
cmd: false
argument_hint: null
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

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
ctk-build — Build inner CTK only, skip external deps (no arguments)

Usage:
  /ctk-build                    Incremental inner CTK build (~1 min)

Prereq: superbuild must have completed once via /ctk-superbuild
```

Build only the inner CTK project, skipping external dependency rebuilds. This is much faster than the superbuild for iterating on CTK source changes.

## Prerequisites

The superbuild must have completed at least once (via `/ctk-superbuild`) so that all external dependencies are built. The build must be configured with `CMAKE_OSX_SYSROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk` for clazy compatibility.

## Steps

### Step 1: Build

```bash
cd ~/src/CTK && cmake --build cmake-build-clazy/CTK-build -j8
```

This typically completes in under a minute for incremental builds.

### Step 2: Report

If the build succeeds, report success with the number of compilation units.
If the build fails, show the last 40 lines of output and identify the failing target/file.

## Arguments

If the user passes a target name (e.g., `/ctk-build CTKWidgetsCppTests`), append `--target <target>` to the cmake build command.
