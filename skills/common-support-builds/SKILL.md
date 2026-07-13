---
name: common-support-builds
version: 1.0.0
purpose: Manage a shared library tree at ~/src/common_support_versions/ where pre-built packages (ITK, VTK, Eigen, DCMTK, HDF5, FFTW, TBB, etc.) are installed at specific git tags for reuse across multiple project builds via USE_SYSTEM_* CMake variables.
description: >-
  Manage a shared library tree at ~/src/common_support_versions/ where
  pre-built packages (ITK, VTK, Eigen, DCMTK, HDF5, FFTW, TBB, etc.) are
  installed at specific git tags for reuse across multiple project builds via
  USE_SYSTEM_* CMake variables. Handles cloning sources, creating worktrees
  for tags, configuring via CMakeUserPresets.json, building in Release mode
  with -mtune=native -march=native, installing, and updating consumer
  projects' CMakeUserPresets.json to point at the installed trees.
  Use this skill whenever the user mentions: common_support_versions,
  USE_SYSTEM_* builds, shared dependency builds, pre-built ITK/VTK for
  testing, "build ITK at tag X for reuse", system package builds,
  performance-optimized dependency builds, ASAN dependency builds,
  "I need ITK built at v5.4.2 for BRAINSTools", building dependencies
  once for multiple consumers, or managing multiple versions of the same
  library side by side. Also trigger when the user wants to set up a new
  build variant (ASAN, performance, minimal) that should reuse pre-built
  dependencies instead of rebuilding them from scratch via SuperBuild.
triggers:
  - common-support-builds
  - /common-support-builds
user_invocable: true
cmd: false
argument_hint: "<package> <tag> [--variant asan|release|debug]"
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

# Common Support Builds

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
common-support-builds — Pre-build shared dependencies at specific tags

Usage:
  /common-support-builds ITK v5.4.2         Build ITK at tag v5.4.2
  /common-support-builds VTK v9.4.0         Build VTK at tag v9.4.0
  /common-support-builds ITK v5.4.2 --variant asan   ASAN variant
  /common-support-builds --status           Show installed packages
```

Manage a local tree of pre-built packages so that multiple projects
(BRAINSTools, Slicer modules, standalone tests, performance harnesses)
can share the same compiled dependencies via `USE_SYSTEM_*` CMake variables
instead of each project rebuilding them from source.

## Scripts (use these — do not manually compose JSON)

| Script | Purpose |
|--------|---------|
| `scripts/csv_pixi_init.sh` | **First time setup.** Create Pixi environment with conda-forge deps |
| `scripts/csv_resolve_deps.py` | Resolve dependency tree: CSV > Pixi > Homebrew > build |
| `scripts/csv_show_dep_tree.py` | **Display after every build.** Visual dependency tree with resolution status |
| `scripts/csv_scaffold.sh` | Create directory tree (clone, worktree, build/install dirs) |
| `scripts/csv_gen_presets.py` | Generate/update CMakeUserPresets.json in source tree |
| `scripts/csv_update_consumer.py` | Patch a consumer project's CMakeUserPresets.json to point at installed packages |

All scripts are in this skill's directory. Always use them rather than
manually writing JSON or mkdir commands.

The dependency graph is in `references/dependency-graph.json`.

## Why this exists

SuperBuild projects like BRAINSTools and Slicer compile ITK, VTK, and a
dozen other libraries as ExternalProjects. When you maintain several build
variants (Debug inner, Release inner, ASAN, performance benchmarks), each
one either re-downloads and rebuilds those dependencies or requires careful
manual wiring. This skill automates the "build once, use everywhere" pattern
by maintaining a canonical tree of installed packages at known git tags.

## Directory layout

```
~/src/common_support_versions/
└── <PKG>/                          # e.g. ITK, VTK, Eigen3, DCMTK
    ├── src_main/                   # primary git clone (default branch)
    ├── src_<GIT_TAG>/              # git worktree at a specific tag
    ├── bld_<GIT_TAG>/             # build directory for that tag
    ├── bld_<GIT_TAG>_<FEATURE>/   # build with non-default feature suffix
    ├── installed_<GIT_TAG>/       # install prefix for that tag
    ├── installed_<GIT_TAG>_<FEATURE>/  # install with feature suffix
    └── installed_main/            # install from HEAD of default branch
```

### Naming rules

| Component | Format | Example |
|-----------|--------|---------|
| Package dir | UPPERCASE or as canonical | `ITK`, `VTK`, `Eigen3` |
| Git tag | verbatim tag name, dots OK | `v5.4.2`, `v9.4.0` |
| Feature suffix | `_FEATURE` appended | `_shared`, `_clang19`, `_asan` |

### When to add a feature suffix

A suffix is required **only** when a build option changes the public API or
ABI in a way that is incompatible with the default build. The test: "can a
consumer built against the default also link against this variant without
recompiling?" If no, add a suffix.

**Requires suffix (API/ABI-incompatible):**
- `BUILD_SHARED_LIBS=ON` → suffix `_shared`
- Non-default compiler → suffix `_<compiler><version>` (e.g., `_gcc14`, `_clang19`)
- `CMAKE_CXX_STANDARD=20` when default is 17 → suffix `_cxx20`
- Sanitizer instrumentation → suffix `_asan`, `_tsan`, `_ubsan`

**No suffix needed (additive, API-compatible):**
- Enabling additional modules (`Module_ITKTBB=ON`, `Module_ITKFEM=ON`)
- Enabling wrapping (`ITK_WRAP_PYTHON=ON`) — adds targets, doesn't change C++ API
- Changing `BUILD_TESTING`, `BUILD_EXAMPLES`
- Changing install prefix or data paths

When in doubt, **do not add a suffix** — reconfigure the existing build
directory to add the new component. This keeps the tree lean.

## Default build configuration

All builds in this tree share these defaults:

```
CMAKE_BUILD_TYPE              = Release
CMAKE_CXX_FLAGS               includes -mtune=native -march=native
CMAKE_C_FLAGS                 includes -mtune=native -march=native
CMAKE_OSX_DEPLOYMENT_TARGET   = 15.0  (macOS only, auto-set by csv_gen_presets.py)
Generator                     = Ninja
Compiler                      = system default (Apple Clang on macOS, GCC on Linux)
BUILD_TESTING                 = OFF
BUILD_EXAMPLES                = OFF
BUILD_SHARED_LIBS             = OFF
```

`CMAKE_OSX_DEPLOYMENT_TARGET=15.0` is set automatically by the preset
generator on macOS. This ensures all CSV builds and their consumers link
with the same deployment target, preventing "built for newer macOS"
linker warnings. When not explicitly specified, **always use 15.0**.

Testing and examples are OFF because these are dependency builds —
correctness is verified in the consuming project's tests, not here.

## CMakeUserPresets.json as the primary configuration mechanism

Every source tree in `common_support_versions` gets a `CMakeUserPresets.json`
that is the **sole** configuration mechanism. Do not pass `-D` or `-C` flags
on the cmake command line — put everything in the preset file.

This file is not tracked by git (it is in `.gitignore` for most CMake
projects). The skill creates and maintains it.

### Preset structure

Use CMake Presets version 3 (requires CMake 3.22+). The preset hierarchy:

```
csv_base                          ← shared defaults (Release, native flags, Ninja)
  ├── csv_<PKG>_<TAG>            ← tag-specific config (binaryDir, installPrefix)
  └── csv_<PKG>_<TAG>_<FEAT>    ← feature-variant (overrides specific vars)
```

The `csv_` prefix (Common Support Versions) avoids collisions with any
project-defined presets.

### Template for csv_base preset

```json
{
  "name": "csv_base",
  "hidden": true,
  "generator": "Ninja",
  "cacheVariables": {
    "CMAKE_BUILD_TYPE":      {"type": "STRING", "value": "Release"},
    "CMAKE_CXX_FLAGS":       {"type": "STRING", "value": "-mtune=native -march=native"},
    "CMAKE_C_FLAGS":         {"type": "STRING", "value": "-mtune=native -march=native"},
    "BUILD_TESTING":         {"type": "BOOL",   "value": "OFF"},
    "BUILD_EXAMPLES":        {"type": "BOOL",   "value": "OFF"},
    "BUILD_SHARED_LIBS":     {"type": "BOOL",   "value": "OFF"},
    "CMAKE_EXPORT_COMPILE_COMMANDS": {"type": "BOOL", "value": "ON"}
  }
}
```

### Template for tag-specific preset (ITK example)

```json
{
  "name": "csv_ITK_v5.4.2",
  "inherits": "csv_base",
  "displayName": "ITK v5.4.2 (Release, static, native)",
  "binaryDir": "${sourceDir}/../bld_v5.4.2",
  "cacheVariables": {
    "CMAKE_INSTALL_PREFIX": {"type": "PATH", "value": "/Users/johnsonhj/src/common_support_versions/ITK/installed_v5.4.2"},
    "ITK_LEGACY_REMOVE":   {"type": "BOOL", "value": "ON"},
    "ITK_BUILD_DEFAULT_MODULES": {"type": "BOOL", "value": "ON"}
  }
}
```

### Template for feature-variant preset

```json
{
  "name": "csv_ITK_v5.4.2_shared",
  "inherits": "csv_ITK_v5.4.2",
  "displayName": "ITK v5.4.2 (Release, shared, native)",
  "binaryDir": "${sourceDir}/../bld_v5.4.2_shared",
  "cacheVariables": {
    "CMAKE_INSTALL_PREFIX": {"type": "PATH", "value": "/Users/johnsonhj/src/common_support_versions/ITK/installed_v5.4.2_shared"},
    "BUILD_SHARED_LIBS": {"type": "BOOL", "value": "ON"}
  }
}
```

## Recursive dependency resolution

Builds are **recursive**: when building ITK, its own dependencies (Eigen,
ZLIB, HDF5, TBB, etc.) should also come from pre-built sources rather than
being compiled internally. This avoids redundant builds and ensures all
consumers share identical dependency versions.

### Dependency strategy (in priority order)

1. **Already installed in `common_support_versions/`** — use it directly
2. **Pixi environment (conda-forge)** — preferred for reproducibility;
   provides pinned versions of Eigen, ZLIB, PNG, JPEG, TIFF, Expat,
   DoubleConversion, HDF5, TBB, FFTW, SWIG, CastXML, DCMTK, GDCM,
   GoogleTest. Lives at `~/src/common_support_versions/.pixi/envs/default/`.
3. **Homebrew** — fallback when Pixi env is not set up
4. **Build from source** — last resort, for packages not in any manager
   or when a specific patched version is required

### Version compatibility for system packages

Homebrew and Pixi may provide newer versions than what the consumer was
built against. This is acceptable when **MAJOR.MINOR** versions match.
For example:
- ITK v5.4.2 requests Eigen `>=3.3` → Eigen 3.4.x from conda-forge is OK
- HDF5 1.14.x from Homebrew is compatible with code expecting HDF5 1.14.y
- Eigen **5.0.1** from Homebrew is NOT compatible with ITK requesting 3.3

When a system package's major version is too new (as happened with
Homebrew Eigen 5.x vs ITK's Eigen 3.x requirement), override that
single dep: `ITK_USE_SYSTEM_EIGEN=OFF` while keeping the rest ON.
The resolver does not currently check version compatibility
automatically — verify CMake configure output for version mismatches.

### First-time setup: Pixi environment

```bash
# Install all deps for the whole ecosystem:
scripts/csv_pixi_init.sh

# Or just for one package:
scripts/csv_pixi_init.sh --pkg ITK
```

This creates `~/src/common_support_versions/pixi.toml` and runs
`pixi install` to materialize the conda-forge environment. The resolver
auto-detects this environment at `.pixi/envs/default/`.

### Step 0: Always resolve dependencies first

Before building any package, run the dependency resolver:

```bash
# Default: Pixi preferred, Homebrew fallback
python3 scripts/csv_resolve_deps.py --pkg ITK --tag v5.4.2

# Skip Pixi, use Homebrew only:
python3 scripts/csv_resolve_deps.py --pkg ITK --tag v5.4.2 --no-pixi

# No package managers — only CSV installs or build from source:
python3 scripts/csv_resolve_deps.py --pkg ITK --tag v5.4.2 --no-pixi --no-homebrew
```

This prints a table showing each dependency's status (CSV/PIXI/BREW/BUILD).
Build anything marked BUILD before proceeding to the target package.

To generate CMake preset variables for all satisfied deps:

```bash
python3 scripts/csv_resolve_deps.py --pkg ITK --tag v5.4.2 --emit-preset-vars
```

This outputs JSON you can merge into the package's `CMakeUserPresets.json`
(or pass as `--cache-var` arguments to `csv_gen_presets.py`).

### Recursive build example: BRAINSTools → ITK → deps

```bash
# 1. Set up Pixi environment (one-time)
scripts/csv_pixi_init.sh --pkg BRAINSTools

# 2. Resolve what BRAINSTools needs (recursively includes ITK's deps)
python3 scripts/csv_resolve_deps.py --pkg BRAINSTools --tag main

# 3. Build anything marked BUILD (leaves first):
#    e.g., DCMTK, then ITK (with PIXI/BREW deps wired in), then ANTs

# 4. For ITK, generate preset vars from satisfied deps:
python3 scripts/csv_gen_presets.py --pkg ITK --tag v5.4.2 \
  --source-dir .../src_v5.4.2 --build-dir .../bld_v5.4.2 \
  --install-dir .../installed_v5.4.2 \
  --cache-var "ITK_USE_SYSTEM_LIBRARIES:BOOL=ON" \
  --cache-var "ITK_USE_SYSTEM_EIGEN:BOOL=OFF"   # if Eigen version incompatible

# 5. Build ITK, then wire into BRAINSTools

# 6. ALWAYS display the dependency tree after a build completes:
python3 scripts/csv_show_dep_tree.py --pkg BRAINSTools --tag main
```

### Displaying the dependency tree

**After every build**, run `csv_show_dep_tree.py` to display the resolved
dependency tree. This is a required step — it shows the user exactly which
deps came from where (CSV install, Pixi, Homebrew, or built from source).

```bash
python3 scripts/csv_show_dep_tree.py --pkg ITK --tag v5.4.2
```

The tree uses Unicode box-drawing characters and status icons:
- `●` CSV — installed in common_support_versions
- `◆` PIXI — conda-forge via Pixi
- `▲` BREW — Homebrew
- `✗` BUILD — needs building from source
- `○` INTERNAL — built internally by parent

When invoked with ANSI color support (terminal), each status gets a
distinct color. Use `--no-color` for plain text.

### The dependency graph

The graph is in `references/dependency-graph.json`. It maps each package
to its dependencies with:
- `use_system_var` — the CMake variable to set ON
- `find_var` — the `*_DIR` or `*_ROOT` hint variable
- `category` — build cost (header-only, tiny, medium, large, build-tool)
- `conda_pkg` — conda-forge package name for Pixi
- `homebrew_pkg` — Homebrew formula name (null if unavailable)

Currently covers: ITK, VTK, BRAINSTools, ANTs, Slicer, CTK.

## Procedure

### 1. Scaffold the directory tree

Run the scaffolding script (see `scripts/csv_scaffold.sh`):

```bash
scripts/csv_scaffold.sh <PKG> <GIT_TAG> [--repo <GIT_URL>]
```

This:
- Creates `~/src/common_support_versions/<PKG>/` if needed
- Clones `src_main` if no primary clone exists (prompts for repo URL if not given)
- Creates `src_<GIT_TAG>` as a git worktree from the primary clone
- Creates empty `bld_<GIT_TAG>` and `installed_<GIT_TAG>` directories

If a feature suffix is needed, pass `--feature <SUFFIX>`:
```bash
scripts/csv_scaffold.sh ITK v5.4.2 --feature shared
```

### 2. Generate or update CMakeUserPresets.json

After scaffolding, generate the presets file in the source worktree.
The generator script (see `scripts/csv_gen_presets.py`) reads the
existing `CMakeUserPresets.json` (if any) and merges in the new preset
without disturbing existing presets.

```bash
python3 scripts/csv_gen_presets.py \
  --pkg ITK \
  --tag v5.4.2 \
  --source-dir ~/src/common_support_versions/ITK/src_v5.4.2 \
  --build-dir  ~/src/common_support_versions/ITK/bld_v5.4.2 \
  --install-dir ~/src/common_support_versions/ITK/installed_v5.4.2 \
  [--feature shared] \
  [--cache-var "BUILD_SHARED_LIBS:BOOL=ON"] \
  [--cache-var "ITK_WRAP_PYTHON:BOOL=ON"] \
  [--compiler /opt/homebrew/opt/llvm/bin/clang++]
```

If `--compiler` is specified and differs from the system default, the
script automatically adds the appropriate feature suffix to preset names.

### 3. Configure

```bash
cmake --preset csv_ITK_v5.4.2
```

That's it. No `-D` flags, no `-C` init-cache files. The preset contains
everything.

### 4. Build

```bash
cmake --build --preset csv_ITK_v5.4.2 -j$(sysctl -n hw.logicalcpu)
```

Or equivalently:
```bash
ninja -C ~/src/common_support_versions/ITK/bld_v5.4.2 -j$(sysctl -n hw.logicalcpu)
```

### 5. Install

```bash
cmake --install ~/src/common_support_versions/ITK/bld_v5.4.2
```

### 6. Update consumer projects — ALWAYS use csv_update_consumer.py

After installing a package, run `scripts/csv_update_consumer.py` to patch
the consuming project's `CMakeUserPresets.json`. Do not manually edit the
consumer's preset JSON — the script handles path resolution, backup, and
correct variable naming.

```bash
# Wire a single package into a consumer:
python3 scripts/csv_update_consumer.py \
  --consumer-source ~/src/BRAINSTools \
  --preset-name base_language \
  --pkg ITK --tag v5.4.2 \
  --use-system

# Wire multiple packages (run once per package):
python3 scripts/csv_update_consumer.py \
  --consumer-source ~/src/BRAINSTools \
  --preset-name base_language \
  --pkg ITK --tag v5.4.2 --use-system

python3 scripts/csv_update_consumer.py \
  --consumer-source ~/src/BRAINSTools \
  --preset-name base_language \
  --pkg VTK --tag v9.4.0 --use-system
```

The script automatically:
- Resolves the CMake config directory (e.g., `lib/cmake/ITK-5.4/`) via glob
- Sets `<PKG>_DIR` pointing to the installed tree
- Sets the `USE_SYSTEM_*` variable to `ON` when `--use-system` is passed
- Backs up the existing `CMakeUserPresets.json` before modifying

For feature-suffixed builds, pass `--feature`:
```bash
python3 scripts/csv_update_consumer.py \
  --consumer-source ~/src/BRAINSTools \
  --preset-name base_language \
  --pkg ITK --tag v5.4.2 --feature shared --use-system
```

#### Reference: Package → variable mapping

| Package | DIR variable | USE_SYSTEM variable |
|---------|-------------|-------------------|
| ITK | `ITK_DIR` | `USE_SYSTEM_ITK` |
| VTK | `VTK_DIR` | `USE_SYSTEM_VTK` |
| Eigen3 | `Eigen3_DIR` | `ITK_USE_SYSTEM_EIGEN` |
| DCMTK | `DCMTK_DIR` | `ITK_USE_SYSTEM_DCMTK` |
| HDF5 | `HDF5_DIR` | `ITK_USE_SYSTEM_HDF5` |
| FFTW | `FFTW_DIR` | `ITK_USE_SYSTEM_FFTW` |
| TBB | `TBB_DIR` | `USE_SYSTEM_TBB` |
| GDCM | `GDCM_DIR` | `ITK_USE_SYSTEM_GDCM` |

#### SuperBuild consumers (BRAINSTools, Slicer)

For SuperBuild projects, `USE_SYSTEM_ITK=ON` and `ITK_DIR` at the
SuperBuild level cause it to skip the ExternalProject download entirely.
The consumer update script works the same way — it patches the named
preset in the SuperBuild's `CMakeUserPresets.json`.

### 7. Adding modules to an existing build

If you need to enable an additional module (e.g., `Module_ITKTBB=ON`) that
does not change the public API:

1. Edit `CMakeUserPresets.json` in the source tree — add the variable to
   the existing preset (do **not** create a new preset or suffix)
2. Reconfigure: `cmake --preset csv_ITK_v5.4.2`
3. Rebuild and reinstall

This avoids directory proliferation for compatible additions.

## Package-specific notes

### ITK

Read `Documentation/AI/building.md` in the ITK source for full build
guidance. Key ITK-specific variables to consider for the preset:

```json
"ITK_LEGACY_REMOVE":              {"type": "BOOL", "value": "ON"},
"ITK_FUTURE_LEGACY_REMOVE":       {"type": "BOOL", "value": "ON"},
"GDCM_LEGACY_REMOVE":             {"type": "BOOL", "value": "ON"},
"ITK_BUILD_DEFAULT_MODULES":      {"type": "BOOL", "value": "ON"},
"ITK_USE_SYSTEM_ZLIB":            {"type": "BOOL", "value": "ON"},
"ITK_USE_SYSTEM_UUID":            {"type": "BOOL", "value": "ON"}
```

For ITK with Python wrapping (no feature suffix needed — additive):
```json
"ITK_WRAP_PYTHON": {"type": "BOOL", "value": "ON"}
```

### VTK

VTK's module system is similar. Disable optional GUI modules for
headless dependency builds:
```json
"VTK_GROUP_ENABLE_Rendering": {"type": "STRING", "value": "DONT_WANT"},
"VTK_GROUP_ENABLE_Qt":        {"type": "STRING", "value": "NO"}
```

### Eigen3

Eigen is header-only — the "build" is really just a configure+install
to set up the CMake package config. It builds in seconds.

## Cross-platform notes

- macOS: system default compiler is Apple Clang (`/usr/bin/clang++`).
  Homebrew LLVM at `/opt/homebrew/opt/llvm/bin/clang++` is a non-default
  compiler requiring a `_clang<VER>` suffix.
- Linux: system default is typically `g++`. Specifying `clang++` from a
  non-system path requires a suffix.
- Use `sysctl -n hw.logicalcpu` (macOS) or `nproc` (Linux) for `-j`.

## Quality checks

After building and installing, verify:
- [ ] `installed_<TAG>/lib/cmake/<PKG>*/` contains `*Config.cmake`
- [ ] Consumer project configures successfully with `USE_SYSTEM_<PKG>=ON`
- [ ] No `-D` flags were used on any cmake command line
- [ ] CMakeUserPresets.json in both source and consumer trees are valid JSON

## Enhanced by

- **context7** — When installed, can fetch current documentation for
  build tools, CMake, and libraries to provide more accurate guidance.
  Falls back to training data when unavailable.
