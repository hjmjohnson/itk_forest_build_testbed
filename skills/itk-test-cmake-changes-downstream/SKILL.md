---
name: itk-test-cmake-changes-downstream
version: 1.0.0
purpose: 'Prove an ITK exported/installed-CMake change (ThirdParty export code, UseITK, ITKModuleMacros, ITKConfig, exported targets) does not break downstream consumers — or pinpoint which consumption pattern it changes — by sweeping a family of fake consumers against both the ITK build tree and install tree, artifact-scored, with optional differential A/B variant comparison.'
description: >-
  Use when an ITK pull request changes exported/installed CMake — especially
  ThirdParty modules (ZLIB, PNG, HDF5, TIFF, GDCM, Eigen3, ...), their
  *_EXPORT_CODE_INSTALL / *_EXPORT_CODE_BUILD blocks, UseITK, ITKModuleMacros,
  or any ITKConfig / module-config / exported-target generation — and you need
  to prove the change either does not break downstream consumers or to surface
  exactly which consumption pattern it changes. Builds a tiny ITK twice
  (ITK_USE_SYSTEM_<dep> ON and OFF), installs it, and sweeps a family of fake
  downstream consumers (modern find_package, legacy UseITK + ITK_LIBRARIES,
  CONFIG/NO_MODULE, COMPONENTS, direct ITK:: target, and a "naive third-party
  piggyback" canary) against BOTH the build tree and the install tree, scored
  PASS/FAIL by artifact. Supports differential A/B comparison of the PR tree
  against a baseline so constants cancel. Keywords: ITK export CMake change,
  downstream breakage, find_package(ITK), ITK_USE_FILE, ITK_LIBRARIES,
  ZLIB::ZLIB, install tree vs build tree, EXPORT_CODE_INSTALL, retain zlib,
  modern CMake interface migration, ThirdParty module consumption.
triggers:
  - itk-test-cmake-changes-downstream
  - /itk-test-cmake-changes-downstream
  - test ITK cmake change downstream
  - does this ITK export change break downstreams
  - downstream consumer matrix
  - build tree vs install tree consumer
user_invocable: true
cmd: false
argument_hint: '<itk-worktree-dir>'
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - .devlocal/
      - Modules/ThirdParty/*/CMakeLists.txt
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: true
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
    - ninja
    - ccache
    - pixi
  python_packages: []
  scripts:
    - bin/run-downstream-matrix.sh
deployment:
  tier: always
  target_projects: []
  needs_loader_dir: true
  adapters:
    - claude-code
---

> The `modifies_working_tree` side effect is the temporary, **restored** swap of
> a `Modules/ThirdParty/<X>/CMakeLists.txt` during the A/B differential (the
> orchestrator runs `git checkout --` to restore it); all build output and
> installs live under the ITK worktree's git-ignored `.devlocal/` scratch.

# itk-test-cmake-changes-downstream

## Overview

ITK is mid-migration from variable-based (`${ITK_LIBRARIES}` + `UseITK.cmake`)
to modern target-based (`ITK::ITK<Module>`) CMake. A change to ITK's exported
or installed CMake can be invisible to ITK's own build yet break a downstream
project — and build-tree consumption can behave differently from install-tree
consumption (ITK emits *separate* `*_EXPORT_CODE_BUILD` and
`*_EXPORT_CODE_INSTALL` blocks).

This skill is the **fast, targeted** complement to the heavyweight forest
testbed (`~/src/itk_forest_build_testbed/bin/run-matrix.sh`, which builds real
ANTs/Slicer/elastix/... and takes hours). It builds a minimal ITK and sweeps a
**family of fake consumers** in minutes, isolating one export-CMake concern.

Core principle (shared with the forest testbed): **score by artifact, never by
pipe exit code.** A consumer PASSES iff its executable exists on disk.

## When to use

- A PR edits `Modules/ThirdParty/<X>/CMakeLists.txt` export code, an
  `itk-module.cmake`, `CMake/ITKModuleMacros.cmake`, `UseITK.cmake`,
  `ITKConfig.cmake.in`, or anything that changes generated consumer-facing
  CMake.
- You are skeptical a "harmless cleanup" is harmless (e.g. removing a
  `find_package(<dep>)` from exported config).
- You need to decide between *notify downstreams* and *confirm safe*.

## The fake-consumer family

Each consumer is a 6-line project that compiles one probe `.cxx` forcing the
dependency (default: `probe_zlib.cxx` -> `itk_zlib.h` -> `zlibVersion()`).
Every consumer is built against **both** the ITK build tree and the ITK install
tree. The family mirrors the idioms actually found in the forest
(`~/src/itk_forest_build_testbed/forest_git_repos/*/CMakeLists.txt`):

| consumer | idiom | real-world matches | what it detects |
|---|---|---|---|
| `modern_libraries` | `find_package(ITK)` + `target_link_libraries(${ITK_LIBRARIES})` | BioCell, Cleaver, HASI, RTK, most remotes | whole-ITK link/include regressions |
| `legacy_usefile` | `+ include(${ITK_USE_FILE})` | c3d, elastix, LesionSizingToolkit | UseITK include/var plumbing |
| `config_nomodule` | `find_package(ITK NO_MODULE)` + UseITK | IGSIO | CONFIG-mode resolution |
| `components` | `find_package(ITK COMPONENTS <m>)` + UseITK | elastix, RTK | per-component subtree export |
| `direct_target` | `target_link_libraries(ITK::ITK<X>Module)` | most-modern style | the interface target's own usage requirements |
| `naive_thirdparty` | links `<DEP>::<DEP>` with **no** own `find_package(<dep>)` | a consumer that piggy-backs on ITK re-discovering the dep | **canary**: whether ITK still injects the upstream imported target into consumer scope, and whether build tree vs install tree diverge |

The `naive_thirdparty` canary is the one that exposes a removed
`find_package(<dep>)` from exported config and any **build-tree vs install-tree
asymmetry**.

## How to run

```bash
ITKSRC=<itk worktree>                 # the PR checkout
SK=<this skill dir>
SCR=$ITKSRC/.devlocal/zlib-matrix     # gitignored scratch

# 1. Build a MINIMAL ITK twice (system dep ON and OFF). Module flags below
#    enable a ThirdParty consumer of the dep; ITK 6.0 still pulls the ImageIO
#    group, which is fine.
ARGS="-GNinja -DCMAKE_BUILD_TYPE=Release -DITK_USE_CCACHE=ON \
  -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
  -DBUILD_TESTING=OFF -DITK_BUILD_DEFAULT_MODULES=OFF -DModule_ITKIOPNG=ON"
pixi run cmake -B $SCR/build-on  -S $ITKSRC $ARGS -DITK_USE_SYSTEM_ZLIB=ON
pixi run cmake -B $SCR/build-off -S $ITKSRC $ARGS -DITK_USE_SYSTEM_ZLIB=OFF
pixi run cmake --build $SCR/build-on   # and build-off
pixi run cmake --install $SCR/build-on --prefix $SCR/inst-on

# 2. Sweep all consumers against build tree + install tree, artifact-scored.
bash $SK/bin/run-downstream-matrix.sh \
     --build $SCR/build-on --install $SCR/inst-on --label on
```

`run-downstream-matrix.sh` prints a PASS/FAIL table and keeps per-cell
configure/build logs at `<--out>.logs/`.

### Differential A/B method (the rigorous part)

A single PASS/FAIL snapshot is muddied by *constants* (unrelated install or
build quirks — see below). To attribute a change to the PR, run the SAME sweep
against **two or three ITK variants** and compare columns:

- **C = baseline** — `git show origin/main:Modules/ThirdParty/<X>/CMakeLists.txt`
- **A = the PR** — HEAD
- **B = an alternative fix** — e.g. emptying *both* INSTALL and BUILD export
  blocks

The export code is generated at *configure* time, so switching variants is
cheap: drop the variant `CMakeLists.txt` into the ITK source, `pixi run cmake
<build-dir>` (regenerates config text, no recompile), `cmake --install`, sweep.
See `examples/orchestrate.sh` for the loop. **A cell that is identical between C
and A is unaffected by the PR**, regardless of whether it PASSes or FAILs in
absolute terms.

## Interpreting results — worked example (PR #6489, "retain zlib")

PR #6489 emptied `ITKZLIB_EXPORT_CODE_INSTALL` (removed `find_package(ZLIB)`
from the *installed* ITK config) while leaving `ITKZLIB_EXPORT_CODE_BUILD`
intact. Full matrix in `examples/pr6489-zlib-results.txt`. Differential:

```
consumer          tree         C:base   A:PR     B:both-empty   PR vs baseline
modern_libraries  build/inst   PASS     PASS     PASS           same
legacy_usefile    build/inst   PASS     PASS     PASS           same
config_nomodule   build/inst   PASS     PASS     PASS           same
components        install      PASS     PASS     PASS           same
direct_target     build/inst   PASS     PASS     PASS           same
naive_thirdparty  buildtree    PASS     PASS     FAIL           same
naive_thirdparty  installtree  PASS     FAIL     FAIL           CHANGED  <-- the signal
```

Conclusion the matrix proves:
- **Every standard idiom is unchanged** by the PR -> safe for ANTs/Slicer/
  elastix/remote-module style consumers.
- The **only** behavioral change is `naive_thirdparty` on the **install tree**:
  a consumer that links `ZLIB::ZLIB` *without its own* `find_package(ZLIB)`,
  relying on ITK to provide it. Under the PR that consumer still configures
  against ITK's **build tree** (BUILD export still runs `find_package(ZLIB)`)
  but fails against the **install tree** -> the build-vs-install **asymmetry**.
- Variant **B** (empty both blocks) makes it symmetric (fails in both trees).

Reviewer action this drives: the PR is safe to land for correct consumers;
either also empty the BUILD block (symmetry) or document that downstreams using
`ZLIB::ZLIB` directly must call their own `find_package(ZLIB)`.

## Retargeting at another ThirdParty module

The family is parameterized; override per-dependency and point the probe at a
header that pulls that dep:

```bash
PROBE_SRC=$SK/consumers/probe_hdf5.cxx \
ITK_MODULE_TARGET=ITK::ITKHDF5Module \
THIRDPARTY_TARGET=HDF5::HDF5 \
FIND_COMPONENTS=ITKIOHDF5 \
  bash $SK/bin/run-downstream-matrix.sh --build ... --install ... --label hdf5
```

Add a `probe_<dep>.cxx` that includes the ITK wrapper header (`itk_hdf5.h`,
`itk_tiff.h`, ...) and calls one symbol from the library.

## Known constants (orthogonal noise — do not mis-attribute to the PR)

These appear as FAILs but are **identical across all variants**, so the
differential cancels them. They are properties of the minimal harness / ITK
install, not of the change under test:

- **`components` / buildtree = FAIL-build**: a COMPONENTS-restricted consumer
  in the *build tree* may not get a deep-transitive ThirdParty header
  (`itk_zlib.h`) on its include path; the install tree exports it fine.
- **OpenJPEG install-layout**: ITK installs headers under `include/ITK-X.Y`
  but the vendored OpenJPEG target exports `include/itkopenjpeg-2.5`; whole-
  `${ITK_LIBRARIES}` install consumers error on the missing dir. Work around in
  the harness with `mkdir -p <prefix>/include/itkopenjpeg-2.5` after install
  (see `examples/orchestrate.sh`). Unrelated to any zlib/dep export change.
- **OFF leg, `naive_thirdparty` = FAIL**: with a vendored dep there is no
  `<DEP>::<DEP>` system target at all; expected.

If a FAIL is **not** constant across variants, it is real — investigate it.

## Relationship to the forest testbed

| | this skill | `itk_forest_build_testbed/bin/run-matrix.sh` (forest) |
|---|---|---|
| consumers | synthetic, 6 idioms | real ANTs/Slicer/elastix/SimpleITK/remotes |
| time | minutes | hours |
| isolates | one export-CMake concern, build vs install | end-to-end real builds |
| use | first, on every export-CMake PR | confirmation before landing |

Run this skill first; if it flags a change (or for high-risk export
refactors), confirm with the forest.

## Files

- `consumers/` — the fake-consumer family + `common.cmake` (override knobs) +
  `probe_zlib.cxx`.
- `bin/run-downstream-matrix.sh` — artifact-scored sweep over the family x
  {build tree, install tree}.
- `examples/orchestrate.sh` — the C/A/B variant driver (validated on PR #6489).
- `examples/pr6489-zlib-results.txt` — the validated reference matrix.
