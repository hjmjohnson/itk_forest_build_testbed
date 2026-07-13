---
name: itk-spdx-remote-modules
version: "0.1.0"
purpose: Add SPDX license identifiers to ITK remote module source files
description: >
  Propagate SPDX-FileCopyrightText and SPDX-License-Identifier headers
  to ITK remote module repositories, following VTK's convention of //
  comment lines before the existing license block. Creates a branch, adds
  headers, and opens a PR for each module.
triggers:
  - "add SPDX to remote modules"
  - "SPDX headers for remote module"
  - "propagate SPDX to remote"
user_invocable: true
cmd: false
argument_hint: "[module_name | all]"
contract:
  inputs:
    - Module name or "all" to process all modules under REMOTE_MODULES/
  outputs:
    - Branch with SPDX headers added
    - PR opened against the module's main branch
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "include/*.h"
      - "include/*.hxx"
      - "src/*.cxx"
      - "src/*.h"
      - "test/*.cxx"
      - "wrapping/*.py"
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: true
    network_required: true
    git_required: true
    user_confirmation_required: true
  determinism: hybrid
  cache:
    has_cache: false
    cache_root: ""
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
  scripts: []
deployment:
  tier: project
  target_projects:
    - ITK remote modules
  needs_loader_dir: false
  adapters:
    - claude-code
---

# ITK SPDX Remote Module Propagation

Add SPDX license identifiers to ITK remote module source files, following
the same convention established in ITK main (PR #6063) and VTK.

## Format

**C/C++ files (.h, .hxx, .cxx, .txx):**
```cpp
// SPDX-FileCopyrightText: Copyright NumFOCUS
// SPDX-License-Identifier: Apache-2.0
/*=========================================================================
 *  Copyright NumFOCUS
 ...existing header...
```

**Python files (.py):**
```python
# SPDX-FileCopyrightText: Copyright NumFOCUS
# SPDX-License-Identifier: Apache-2.0
# ==========================================================================
#   Copyright NumFOCUS
...existing header...
```

## Supported copyright patterns

The script adds SPDX headers to files containing:
- `Copyright NumFOCUS` (current standard)
- `Copyright Insight Software Consortium` (legacy, pre-2020)

Files without either pattern are skipped (e.g., vendored code, ThirdParty).

## Procedure

### For a single module:

```
/itk-spdx-remote-modules AdaptiveDenoising
```

### For all modules:

```
/itk-spdx-remote-modules all
```

### What the skill does for each module:

1. **Check the module directory** exists under `REMOTE_MODULES/`
2. **Verify git status** is clean
3. **Create branch** `spdx-file-headers` from `main` (or `master`)
4. **Run the SPDX header script** (adapted from ITK's `AddSPDXHeaders.py`):
   - Scan all `.h`, `.hxx`, `.cxx`, `.txx`, `.py` files
   - Skip files under `ThirdParty/`, `build/`, `cmake-build*/`, `.pixi/`
   - Add SPDX lines only to files with "Copyright NumFOCUS" or
     "Copyright Insight Software Consortium"
   - Skip files that already have "SPDX-License-Identifier"
5. **Commit** with message: `STYLE: Add SPDX license identifiers`
6. **Push** to origin
7. **Open PR** against `main` with standard body

### What the skill does NOT do:

- Does not modify ThirdParty or vendored code
- Does not change the license itself — only adds machine-readable SPDX tags
- Does not modify files that don't have an ITK-standard copyright header
- Does not touch `pyproject.toml` or build configuration

## License detection

The SPDX license identifier is determined by the copyright holder:

| Copyright holder | SPDX-License-Identifier |
|-----------------|------------------------|
| Copyright NumFOCUS | Apache-2.0 |
| Copyright Insight Software Consortium | Apache-2.0 |

All ITK and ITK remote modules use Apache-2.0. Modules with different
licenses (e.g., GPL for FFTW-dependent code) would need manual review.

## Prerequisites

- The module must be cloned under `REMOTE_MODULES/`
- The user must have push access to the module's `origin` remote
- `gh` CLI must be authenticated

## Related

- ITK PR #6063 — SPDX headers for ITK main (5503 files)
- ITK PR #5817 — SBOM generation at configure time
- ITK Issue #4302 — SBOM roadmap
- VTK — uses the same `// SPDX-*` convention
