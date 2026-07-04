# Preset-primary configuration — completion phase (forest-first, A/B-comparison)

**Repo:** `hjmjohnson/itk_forest_build_testbed` (the *kit* repo — not a consumer worktree).
**Date:** 2026-07-04
**Status:** Design approved; implementation not yet started.
**Parent:** [2026-07-03-cmake-presets-restructure-design.md](2026-07-03-cmake-presets-restructure-design.md)
**Supersedes:** the parent spec's Layer-2 overlay decision (`include: [<abs-kit-path>]`).
This phase replaces that with a **flattened, self-contained** overlay (see
"Self-contained forests" below). All other parent decisions stand.

## Purpose that drives every choice

The forest exists to **confirm downstream ITK consumers behave as expected under
different circumstances** — it is an A/B testing rig. The everyday operation is
comparing two sibling trees:

```
build_forest-base   build_forest-itkv5   build_forest-itkv6_main
build_forest-svdc   build_forest-linpackref   ...
```

Every design choice optimizes one question: **how easily can I diff
`build_forest-<A>` against `build_forest-<B>` and see exactly what differed** —
in refs, in configuration, and in outcome.

## Two roles, kept strictly separate

| Role | Lives in | Contains |
|---|---|---|
| **Tooling** | `bin/`, `cmake/presets/` (the kit repo) | Utilities that *create*, *configure*, *compare*, and *monitor* forests. The authoring source of truth for `-D` policy. |
| **Environment** | `build_forest-<X>/` | A self-contained A/B test tree: source checkouts, build trees, the **resolved** config it was built with, and **all its logs**. |

**Rules:**

1. A `build_forest-<X>` must be **reviewable on its own** — inspecting how it was
   configured must never require opening `itk_forest_build_testbed/cmake/presets/`.
2. **All logs written for a forest live inside that forest** (`${FOREST}/logs/`).
   No forest log is written to the kit root. (The current kit-root litter —
   `matrix-*.log`, `svdc-linpackref-validation-*.log`, `itk-forest-*.log` — is
   the anti-pattern this eliminates.)
3. The kit's `bin/` and `cmake/presets/` are **not part of** any forest. They act
   *on* forests from outside.

## Authoring source vs as-built record (resolves the apparent contradiction)

"Kit fragment is the single source of truth" and "forest is self-contained
without the kit" are both true because they serve different moments:

- **Kit fragment (`cmake/presets/*.json`)** — where `-D` *policy is authored and
  reviewed*, in kit-repo PRs. One place to change what a build *should* be.
- **Forest overlay (flattened, in the forest)** — the *resolved snapshot of what a
  specific forest was actually built with*, reviewed when auditing an A/B run.

Editing a kit fragment does **not** mutate an already-configured forest; the
forest is frozen at its resolved config until an explicit re-resolve. That
freezing is a feature — an A/B data point must not silently drift when policy is
edited later.

## Self-contained forests — the flattened overlay

At configure time the tooling resolves the kit preset chain for a consumer
(base → version → variant, following `inherits`), merges the layered
`cacheVariables` (child wins), overlays the discovered dynamic values, and writes
a **standalone** `CMakeUserPresets.json` into the consumer's forest source dir
with **no `include` back to the kit**:

```jsonc
// build_forest-<X>/ANTs/CMakeUserPresets.json  (globally ignored by name; forest-local)
{
  "version": 8,
  "configurePresets": [{
    "name": "forest-ANTs-local",
    "binaryDir": "${sourceDir}/build",
    "cacheVariables": {
      // --- resolved from cmake/presets/00-base.json + 20-ANTs.json[+variant] ---
      "ANTS_SUPERBUILD": "OFF", "RUN_LONG_TESTS": "ON", "USE_SYSTEM_ITK": "ON",
      "CMAKE_BUILD_TYPE": "Release", "CMAKE_CXX_COMPILER_LAUNCHER": "ccache",
      // --- injected dynamic wiring ---
      "ITK_DIR": "/abs/build_forest-<X>/ITK/build"
    }
  }]
}
```

- What CMake consumes **is** what a reviewer reads — one file, fully resolved,
  self-contained. `$env{...}` macros are preserved verbatim (portable within the
  pixi env and still readable); only genuinely forest-computed paths are concrete.
- Flattening is a small resolver in `bin/config.py` that walks the `inherits`
  chain across the kit fragments and merges `cacheVariables`. It replaces the
  parent spec's `include`-based `write_overlay`.

## Aggregated, diffable record — extend `manifest.toml`

`manifest.toml` already records resolved git SHAs per consumer. Extend it so one
file per forest fully describes **both** what is checked out **and** how it was
configured:

```toml
[components.ANTs]
sha = "…"                     # existing: what is checked out

[config.ANTs]                 # new: how it was configured (resolved -D set)
preset  = "itk-forest-ants-max-modules"     # the selected fragment/variant
ANTS_SUPERBUILD = "OFF"
USE_VTK = "ON"
ITK_DIR = "…"
# … the same flattened cacheVariables written into the overlay …
```

- Written by `bin/config.py` at configure time, from the same resolved map the
  overlay uses (single computation, two sinks — they cannot disagree).
- `python3 bin/config.py compare <forestA> <forestB>` diffs the two
  `manifest.toml` files: ref/SHA deltas **and** `[config.*]` `-D` deltas, in one
  report. This is the everyday A/B operation.

## Logs — `${FOREST}/logs/`

A `forest_log_dir` helper returns `${FOREST}/logs/`; every configure/build/test
and `run-matrix.sh` invocation writes its log there (timestamped,
per-consumer-per-action). `run-matrix.sh`, `setup-itk-downstream-testbed.sh`, and
the validation scripts stop writing to the kit root. Existing kit-root `*.log`
files are swept into their forest's `logs/` (or removed) as a one-time cleanup.

## The preset-primary changes (unchanged intent, now feeding the resolver)

These three changes from the prior draft still apply; they are what make the
resolver's input clean.

### Change 1 — Route ITK through the resolver like every other consumer

Delete the inline `fftw=(…)`, `mods=(…)`, brainweb/testing/examples assembly from
`configure_one()`'s ITK branch; that policy already lives in `10-itk-v5.json` /
`10-itk-v6.json` and becomes their sole home. The ITK branch keeps only: preset
selection (ITK-major → v5/v6/variant), procedural steps (two-pass
fetch-then-`_stub_remote_examples`, `_overlay_vnl_headers`), and `VTK_DIR`
injection. The two-pass configure re-invokes `cmake --preset forest-ITK-local`
around the stub step; the flattened overlay is written once.

### Change 2 — Conditional `-D` bundles become variant presets

| Today (inline `if`) | Variant preset | Inherits |
|---|---|---|
| ITK: VTK present → `Module_ITKVtkGlue=ON` + `BUILD_TESTING/EXAMPLES/BRAINWEB=OFF` | `itk-forest-itk-v6-vtkglue` | `itk-forest-itk-v6` |
| ITK v5: `ITK_WITH_DCMTK=1` → 2 DCMTK modules | `itk-forest-itk-v5-dcmtk` | `itk-forest-itk-v5` |
| ANTs: `ANTS_MAX_MODULES=1` → `USE_VTK=ON`, `BUILD_ALL_ANTS_APPS=ON` | `itk-forest-ants-max-modules` | `itk-forest-ants` |
| BRAINSTools: `BRAINSTOOLS_MAX_MODULES=1` → VTK/DICOM/DWIConvert/GTRACT group | `itk-forest-brainstools-max-modules` | `itk-forest-brainstools` |
| BRAINSTools: `BRAINSTOOLS_NO_ANTS=1` → `USE_ANTS=OFF` | `itk-forest-brainstools-no-ants` | `itk-forest-brainstools` |

The script selects the `inherits` name from the existing env flag; genuinely
dynamic values inside a bundle (`VTK_DIR`, `ANTS_VTK_DIR`, the `USE_SYSTEM_VTK`
fallback + GCC-14 workaround, fork repo/tag) remain injected. Where orthogonal
flags combine (BRAINSTools max-modules *and* no-ants), select the single
appropriate variant and inject the other as a kv rather than multiplying files.

Recording the **selected variant name** in `manifest.toml`'s `[config.<consumer>].preset`
is what makes an A/B diff read as "forest A used `-max-modules`, forest B did
not" at a glance.

### Change 3 — v5 module policy (verify, then adopt)

`10-itk-v5.json` declares the full `ALL_MODULES`+brainweb+testing+examples set
(matching the authoritative rule); the script's v5 path currently does a minimal
`DEFAULT_MODULES` build because v5 remote-module examples call
`find_package(ITK COMPONENTS ITKImageIO)` (no such v5 module) and
`BUILD_TESTING`+BRAINWEB wire an `ITKData` target v5 never creates.

**Resolution (empirical-not-theoretical):** probe a `release-5.4` configure
against the fragment's full set before deleting the inline v5 path. Clean → keep
the fragment; breaks → correct `10-itk-v5.json` to the minimal working set and
express any DCMTK add via the `-dcmtk` variant. Either way the fragment ends as
the single authoring source.

## What explicitly stays in the shell

All `_patch_*` source surgery, `_overlay_vnl_headers`, `_stub_remote_examples`,
PR fetch/`repoint-itk`, the dynamic dir finders (`itk_dir`, `vtk_dir`,
`itk_vtk_dir`, `vkfft_backend`, `_find_nvcc`, IGSIO/OpenIGTLink/vtkAddon), and
`ants_system_args`. These are actions and discovery, not `-D` policy.

## Verification

- **v5:** `release-5.4` configure probe (Change 3) — artifact is a clean
  configure, not a pipe exit.
- **v6:** configure + build ITK in a forest via the resolved overlay; diff the
  resulting `CMakeCache.txt` module entries against the pre-refactor build.
- **Variants:** configure ANTs/BRAINSTools with and without their `*_MAX_MODULES`
  flag; confirm the selected variant's `-D` values land in both the flattened
  overlay and `manifest.toml`'s `[config.*]`.
- **Self-containment:** `grep -L itk_forest_build_testbed build_forest-*/*/CMakeUserPresets.json`
  — no overlay may reference the kit path.
- **A/B utility:** `config.py compare build_forest-itkv5 build_forest-itkv6_main`
  reports the FFTW-on-vs-off and module-set deltas.
- Per kit CLAUDE.md: verify by on-disk artifact; state repo+forest per action.

## Out of scope

- Rewriting `_patch_*` source-surgery functions.
- `workflowPresets` / `run-matrix.sh` full reduction (parent secondary payoff).
- Any consumer upstream-repo change.
