---
name: itk-modernize-use-override
version: 1.0.0
purpose: Sweep ITK and every itk_forest consumer for C++ override-specifier defects (missing override, redundant virtual) with three complementary detectors, one repo and one detector per commit.
description: >-
  Forest-wide application of clang-tidy modernize-use-override, backed by
  compiler -Wsuggest-override / -Winconsistent-missing-override warnings and a
  build-free text scan. Written for a funded, scheduled campaign over the
  itk_forest_build_testbed components (ITK, ANTs, BRAINSTools, elastix, c3d,
  SimpleITK, ITKSNAP, MITK, Slicer, remote modules), not for one-off edits.
  Encodes the pitfalls found proving the approach on ITK PR #6862: modules
  outside the default build, macro-generated overrides clang-tidy cannot fix,
  duplicate "override override" fixes from shared headers, templates only
  seen when instantiated, and bit-rotted optional modules that must be built
  against external dependencies before they can be checked.
triggers:
  - modernize-use-override
  - forest override sweep
  - remove redundant virtual
  - add missing override
  - Wsuggest-override cleanup
  - virtual with override
user_invocable: true
cmd: false
argument_hint: "<component|all> [--forest SUFFIX] [--phase 1|2|3|all] [--fix]"
contract:
  inputs:
    - "Component name from versions.toml (ITK, ANTs, BRAINSTools, ...) or 'all'"
    - "Optional: --forest SUFFIX selecting build_forest-<SUFFIX> (default build_forest)"
    - "Optional: --phase 1|2|3|all (default all)"
    - "Optional: --fix to apply edits; default is report-only"
  outputs:
    - "Per-component report: counts per detector, files touched, TUs that failed to parse"
    - "Up to two local commits per component: one per detector that produced edits"
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "<component worktree>/**/*.h"
      - "<component worktree>/**/*.hxx"
      - "<component worktree>/**/*.cxx"
      - "<component worktree>/**/*.txx"
    writes_outside_repo: true
    writes_outside_repo_paths:
      - "build_forest*/<component>-build/override-sweep/"
    modifies_working_tree: true
    network_required: false
    git_required: true
    user_confirmation_required: true
  determinism: hybrid
  cache:
    has_cache: false
    cache_root: ""
    schema_version: 0
    rebuildable: false
  derivation:
    has_ai_derived_layer: false
    derivation_version: 0
dependencies:
  skills:
    - itk-clang-tidy-refactor
    - itk-start-worktree
    - itk-test-cmake-changes-downstream
  external_tools:
    - clang-tidy
    - run-clang-tidy
    - clang-apply-replacements
    - clang-format
    - cmake
    - ninja
    - git
    - perl
    - python3
  python_packages: []
  scripts:
    - "skills/itk-modernize-use-override/scripts/override_sweep.sh"
    - "skills/itk-modernize-use-override/scripts/find_virtual_with_override.py"
deployment:
  tier: always
  target_projects:
    - ITK
    - ANTs
    - BRAINSTools
    - Slicer
  needs_loader_dir: true
  adapters:
    - claude-code
---

# itk-modernize-use-override

Forest-wide `override` cleanup. State the coordinates for every action:
`Repo: <owner/repo> (<sha>) | Forest: build_forest[-suffix]`.

**Status:** parked until grant funding. ITK itself was proven on
2026-09-15 (PR #6862, follow-up to #6861); run consumers only after
ITK's cleanup is merged, so forest builds see the final ITK headers.

## Why three detectors

No single tool finds everything. Each catches a class the others miss:

| Phase | Detector | Finds | Misses |
|---|---|---|---|
| 1 | clang-tidy `modernize-use-override` | bulk missing `override`, redundant `virtual` | macro expansions (reports, never fixes); TUs that do not compile |
| 2 | `-Wsuggest-override`, `-Winconsistent-missing-override` | macro-generated overrides, template members once instantiated | uninstantiated templates; code not built |
| 3 | `scripts/find_virtual_with_override.py` | redundant `virtual` in any file, no build needed | missing `override`; has known false positives |

Proven yield on ITK: phase 1 fixed 9 headers, phase 2 found 1 macro getter,
phase 3 found nothing new. Phase 2 on an external-VXL build later found 16
more in `vidl_itk_istream.h`, a template only instantiated by a test that
had not compiled for years.

## Rules

1. **One component, one PR.** Never mix repos. Draft PRs only, each
   explicitly approved by the human (`pr-no-unsolicited`).
2. **One detector, one commit.** Subject names the change; the body says
   why (see "Commit messages").
3. **Build before sweeping.** clang-tidy needs `compile_commands.json`
   and generated headers. Re-run `cmake` with
   `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON`; forest builds do not set it.
4. **Maximize what compiles.** Enable every in-tree optional module (see
   "Enabling optional code"); code that is not compiled is not checked.
5. **Exclude vendored code.** `ThirdParty/`, `_deps/`, `*-build/`,
   SuperBuild EP trees, and KWStyle's bundled Boost are upstream's.
6. **Latest upstream first** (testbed non-negotiable): fetch each
   component's main before sweeping.
7. **Never a pre-commit hook.** Phase 3 is a manual sweep. As a hook its
   false positives (comments without `*`, `#if 0`, string literals,
   `override`/`final` as identifiers) block PRs with no per-line
   suppression.

## Procedure per component

### 0. Prepare

```bash
cd ~/src/itk_forest_build_testbed
FOREST_REFERENCE_SUFFIX=<suffix> pixi run checkout          # if not present
git -C build_forest-<suffix>/<Comp> fetch origin && git -C build_forest-<suffix>/<Comp> switch -c override-sweep origin/main
cmake -S build_forest-<suffix>/<Comp> -B build_forest-<suffix>/<Comp>-build \
      -DCMAKE_EXPORT_COMPILE_COMMANDS=ON <optional-module flags>
cmake --build build_forest-<suffix>/<Comp>-build -- -k 0
```

For SuperBuild projects (BRAINSTools, Slicer, ANTs SuperBuild) point the
sweep at the **inner** build tree, e.g. `BRAINSTools-build/BRAINSTools-*-EP*-build`.

### 1. clang-tidy

```bash
skills/itk-modernize-use-override/scripts/override_sweep.sh \
    --src <worktree> --build <build-with-compile_commands> [--fix]
```

The script runs `run-clang-tidy` with `AllowOverrideAndFinal`,
`IgnoreDestructors`, and `IgnoreTemplateInstantiations` all false, exports
fixes, and with `--fix` applies them. It then collapses `override override`:
a header included by many TUs exports the same insertion repeatedly and
`clang-apply-replacements` applies duplicates. Always inspect the diff.

### 2. Compiler warnings

Parse every TU with the warning flags; clang `-fsyntax-only` is fastest:

```bash
-Wsuggest-override -Wsuggest-destructor-override \
-Winconsistent-missing-override -Winconsistent-missing-destructor-override
```

or add `-Wsuggest-override` to `CMAKE_CXX_FLAGS` for a gcc build. Filter
out vendored paths. Macro-generated getters cannot use a macro fix in ITK:
`itkMacro.h` deliberately has no `itkOverride*` variants, so write the
function by hand returning the same member.

### 3. Text scan (optional cross-check)

```bash
skills/itk-modernize-use-override/scripts/find_virtual_with_override.py <worktree>
skills/itk-modernize-use-override/scripts/find_virtual_with_override.py --ref origin/main <worktree>
```

Review each hit against the false-positive list before `--fix`; run
`clang-format` afterwards (removing `virtual` misaligns macro `\` columns).

### 4. Verify

- Rebuild the component; 0 new failures.
- `ctest -R` for every touched module.
- Re-run phase 2: no remaining override warnings in the component's code.
- `pre-commit run --all-files` where the repo has it.
- For ITK: `itk-test-cmake-changes-downstream` is not needed (no API/ABI
  change), but rebuild at least one consumer that subclasses the touched
  headers.

## Enabling optional code (ITK)

Default ITK builds skip about 80 modules. Enable them from the cache:

```bash
comm -23 <(grep -E '^Module_[A-Za-z0-9]+:BOOL=OFF' build/CMakeCache.txt | sed 's/:BOOL=OFF//;s/Module_//' | sort) \
         <(ls Modules/Remote/*.remote.cmake | xargs -n1 basename | sed 's/.remote.cmake//' | sort)
```

Pass each as `-DModule_<name>=ON` (in zsh, expand with `${=VAR}`; an
unquoted `$VAR` is one word). Known blockers:

| Module / option | Needs |
|---|---|
| VtkGlue | VTK; Homebrew VTK needs `-DPython3_EXECUTABLE` at its Python version, and `-DITK_USE_SYSTEM_HDF5=ON` to avoid duplicate HDF5 targets |
| VideoBridgeOpenCV | OpenCV; OpenCV 5 dropped `types_c.h`, so tests fail to compile |
| VideoBridgeVXL | `ITK_USE_SYSTEM_VXL=ON` + upstream `vxl/vxl` master (the ISC fork is numerics-only) built with `VXL_BUILD_CORE_VIDEO=ON -DWITH_FFMPEG=OFF` (vidl's FFmpeg code predates FFmpeg 5). The module itself did not compile as of 2026-09-15 (stashed fix: `itk_module_add_library`, `m_ReadType`→`m_ReadFrom`) |
| BridgeNumPy | Python wrapping |
| GPU modules | `ITK_USE_GPU=ON` + OpenCL |

Toolchain notes: on macOS prefer Apple clang for the build and Homebrew
LLVM only for `clang-tidy`; Homebrew LLVM 23 against the Xcode SDK broke
GDCM and libc++ header lookup under `-isystem /opt/homebrew/include`.
Linux gcc 13 built everything.

## Commit messages

Follow each repo's rules; for ITK, `Documentation/AI/git-commits.md` and
`prose-budget.md`. No AI trailers (`Co-Authored-By` for tools,
`Claude-Session`), no tool narrative in the body. Examples that passed
`kw-commit-msg` and `kw-prose-budget`:

```
STYLE: Apply modernize-use-override to optional modules

These modules are excluded from the default build, so earlier
override cleanups did not reach them.
```

```
STYLE: Mark GPU Yvv GetNormalizeAcrossScale() as override

itkGetConstMacro expands to a virtual getter without override, and
itkMacro.h has no override variant, so the getter is written out.
```

Detection method and test matrix go in the PR body `<details>`; AI
disclosure in its own `<details>` block.

## Baseline (2026-09-15, pattern scan of HEAD, non-vendored hits)

| Repo | Hits |
|---|---|
| ITK (after #6862) | 0 |
| ANTs | 7 |
| BRAINSTools | 4 |
| Slicer | 22 |
| CTK | 13 |
| SimpleITK | 1 |
| VTK (own code) | 4 |

Pattern hits undercount phase 1 and 2 (missing `override` is invisible to
the scan). Re-baseline before starting; counts drift.

## Campaign order

ITK → remote modules in `Modules/Remote` → ANTs, BRAINSTools, elastix,
c3d, SimpleITK → ITKSNAP, MITK → Slicer → SlicerExtensions (triage only;
hundreds of repos, mostly Python). Consumers built against ITK subclass
ITK classes, so ITK first keeps their phase-2 warnings stable.

## ABI / API

Adding `override` or removing a redundant `virtual` from an overriding
member changes neither ABI nor API: the function stays virtual through the
base. Do not remove `virtual` from members that override nothing; the
detectors never propose that, but review hand edits for it.
