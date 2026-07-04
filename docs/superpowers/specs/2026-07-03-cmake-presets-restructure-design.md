# CMakePresets restructure for the ITK forest-build testbed

**Repo:** `hjmjohnson/itk_forest_build_testbed` (the *kit* repo — not a consumer worktree).
**Date:** 2026-07-03
**Status:** Design approved; implementation not yet started.

## Problem

`bin/setup-itk-downstream-testbed.sh` (1078 lines) hand-assembles every
consumer's CMake configuration as shell arrays and heredocs. The largest offender
is `configure_one()` (~280 lines), especially the ITK branch: a ~45-entry
`-DModule_*=ON` array, FFTW flags, a 30-line zlib-hack comment block, and
VTK-conditional wiring — all buried in shell where it cannot be reviewed as
structured data, cannot be run by a human or IDE without the wrapper, and cannot
be shared as a versioned artifact.

`versions.toml` + `bin/config.py` already cleanly own *which ref* each component
builds. This design gives *how to configure* the same treatment: declarative,
reviewable, IDE-runnable CMake presets.

## Goals (from brainstorming)

1. **IDE + human runnability** — `cmake --preset` / `cmake --workflow --preset`
   works in CLion/VSCode/a bare shell without the wrapper.
2. **Shrink/clarify the script** — move declarative config out of shell; leave
   shell only for discovery, source patching, and orchestration.
3. **Human review is critical** — the canonical config lands as reviewable JSON
   in kit-repo PRs.

Ecosystem-health validation (`workflowPresets`) is a secondary payoff, not the
primary driver.

## Non-negotiable constraints carried in

- **State repo + forest for every action** (kit CLAUDE.md). This design touches
  only the *kit* repo. No testbed artifact is ever committed into a consumer
  worktree.
- **Verify by artifact, not pipe exit** (kit CLAUDE.md). `workflowPresets` drive
  builds; the on-disk artifact check in `run-matrix.sh` still scores them. The
  preset does not replace the scorer.
- **Global gitignore** (`~/.gitignore_global`) ignores the literal filenames
  `CMakePresets.json` and `CMakeUserPresets.json`, and the pattern `cmake-*`.

## Directory layout (build nested in source)

This restructure also changes where build and install trees live, because the
new locations are what make the preset `binaryDir`/`installDir` expressible as
native relative macros and unlock the ccache strategy below.

| Tree | Old | New |
|---|---|---|
| Source | `${FOREST}/${PKG}` | `${FOREST}/${PKG}` (unchanged) |
| Build | `${FOREST}/${PKG}-build` | `${FOREST}/${PKG}/build` (nested in source) |
| Install (if used) | `${FOREST}/${PKG}-install` | `${FOREST}/installed/${PKG}` |

In preset macros, from a consumer whose `sourceDir` is `${FOREST}/${PKG}`:

- `binaryDir` = `${sourceDir}/build`
- `installDir` = `${sourceParentDir}/installed/${sourceDirName}`
  (`${sourceParentDir}` = `${FOREST}`, `${sourceDirName}` = `${PKG}`)

Both are **static, identical for every consumer**, so they live in the committed
`00-base.json` — they do **not** go in the generated overlay. Only genuinely
forest-discovered *dirs of other packages* (`ITK_DIR`, `VTK_DIR`, …) remain in
the overlay.

**Why nest build inside source — the ccache rationale (primary driver).** ccache
keys on the compiler command line, which embeds absolute paths. Setting
`CCACHE_BASEDIR` (and a matching `-ffile-prefix-map`) to the **source dir**
rewrites those paths relative to the source root, so the same package built under
two different `FOREST_DIR` locations produces byte-identical compiler inputs and
shares cache entries. `CCACHE_BASEDIR` only rewrites paths **under** its subtree;
a sibling `${PKG}-build` tree would leave the build-dir's own absolute paths
(generated headers, moc/uic outputs, response files) un-rewritten and cache-busting.
Nesting the build under the source (`${sourceDir}/build`) brings the entire
build tree inside the `CCACHE_BASEDIR` subtree, so **every** path is rewritten
and cache hits are maximized per-package across arbitrary forest locations. This
supersedes the earlier forest-relative `-ffile-prefix-map=${FOREST}=.` approach
with a finer-grained per-package source-relative base.

**Global-ignore interaction.** The nested `build/` dir is auto-ignored in every
consumer repo by the global `build` pattern — no extra ignore config, and it will
not show up in a consumer's `git status`.

## Architecture

Three layers, matching the declarative/dynamic boundary that CMakePresets can
and cannot express.

### Layer 1 — Committed, reviewable preset fragments (kit repo)

```
itk_forest_build_testbed/
  cmake/presets/                 # NOTE: cmake/presets (slash), NOT cmake-presets/
    00-base.json                 # hidden: itk-forest-base
    10-itk-v6.json               # hidden: itk-forest-itk-v6 : inherits base
    10-itk-v5.json               # hidden: itk-forest-itk-v5 : inherits base
    consumer-ANTs.json           # hidden configure + build/test/workflow presets
    consumer-Slicer.json
    consumer-<X>.json            # one per consumer
```

- Filenames are **not** the reserved `CMakePresets.json`, so the global ignore
  does not hide them — they are tracked and reviewed in kit-repo PRs.
- Directory is `cmake/presets/` (slash). It must NOT be `cmake-presets/`, which
  the global `cmake-*` pattern would swallow.
- Every fragment preset is `hidden: true`. Only the generated overlay (Layer 2)
  exposes a directly-runnable preset.
- Schema `version: 6` (CMake 3.25+) for `workflowPresets`. The pixi cmake is
  ≥3.28 (Slicer requirement), so this is satisfied.

### Layer 2 — Generated overlay (per consumer forest source dir, gitignored)

At configure time the wrapper discovers the dynamic values and writes a thin
`CMakeUserPresets.json` into the consumer's forest source dir:

```jsonc
// build_forest-<suffix>/ANTs/CMakeUserPresets.json  (globally ignored by name)
{
  "version": 6,
  "include": ["/abs/path/to/kit/cmake/presets/consumer-ANTs.json"],
  "configurePresets": [{
    "name": "forest-ANTs-local",
    "inherits": "itk-forest-ants",
    "cacheVariables": {
      "ITK_DIR": "<discovered>",
      "VTK_DIR": "<discovered>",
      "VkFFT_BACKEND": "<discovered>"
    }
  }]
}
```

- The literal name `CMakeUserPresets.json` is auto-ignored on every machine and
  in every foreign consumer repo by the global rule — no `.git/info/exclude`
  entry needed.
- `include` (schema v4+) lets the reviewable base live in the **kit** repo while
  CMake still resolves it. The `include` path is absolute and stamped per machine
  by the generator; acceptable because the overlay is already machine-local.
- The overlay carries only: the truly forest-computed *other-package* dirs
  (`ITK_DIR`, `VTK_DIR`, …) and the `inherits` selection (v5 vs v6, or the
  consumer fragment). `binaryDir`/`installDir` come from `00-base.json` via
  `${sourceDir}` macros and are **not** repeated here.

### Layer 3 — Shell: discovery, patching, orchestration (stays)

The wrapper keeps everything presets cannot express, and gains one new job:
emit the Layer-2 overlay.

- Dynamic discovery: `itk_dir`, `vtk_dir`, `itk_vtk_dir`, `vkfft_backend`,
  `_find_nvcc`, `openigtlink_dir`, IGSIO/vtkAddon dir finders.
- Source patching: all `_patch_*` functions, `_overlay_vnl_headers`,
  `_stub_remote_examples`, `_fix_dcmtk_ijg_symlinks`, etc.
- Orchestration: PR fetch/`repoint-itk`, the two-pass ITK configure, the
  v5-vs-v6 version gate (a shell one-liner that selects which fragment the
  overlay inherits).
- **Path-computation update:** the wrapper's build/install path variables change
  from `${FOREST}/${name}-build` / `${FOREST}/${name}-install` to
  `${FOREST}/${name}/build` / `${FOREST}/installed/${name}` (`ITK_BUILD`,
  `ITK_INSTALL`, `b="…"` in `configure_one`/`build_one`, `install_itk`, and every
  consumer dir finder that returns a `-build` path). `CCACHE_BASEDIR` is set to
  the per-package source dir — natively via the preset `environment`
  (`"CCACHE_BASEDIR": "${sourceDir}"`), so this needs no shell export.

## Migrate-vs-shell split

| Flag / logic | Destination | Mechanism |
|---|---|---|
| `-G Ninja`, `CMAKE_BUILD_TYPE=Release`, `BUILD_TESTING`, ccache launchers, `CMAKE_IGNORE_PREFIX_PATH=/opt/homebrew` | `00-base.json` | static `cacheVariables` |
| `CC`/`CXX` | `00-base.json` | `$env{CC}` / `$env{CXX}` |
| `CMAKE_BUILD_RPATH=${CONDA_PREFIX}/lib` | `00-base.json` | `$env{CONDA_PREFIX}` in a cacheVar |
| FFTW include/lib search paths | `10-itk-v6.json` | `$env{CONDA_PREFIX}` |
| `binaryDir` = `${sourceDir}/build` | `00-base.json` | native `${sourceDir}` macro |
| `installDir` = `${sourceParentDir}/installed/${sourceDirName}` | `00-base.json` | native macros |
| source-relative ccache base (`CCACHE_BASEDIR` + `-ffile-prefix-map=${sourceDir}=.`) | `00-base.json` `environment` + flags-init | replaces forest-relative `-ffile-prefix-map=${FOREST}=.` |
| `ITK_USE_FFTWD/F=ON`, ~45 `-DModule_*=ON`, `ITK_BUILD_ALL_MODULES`, brainweb, `zlib_hint` | `10-itk-v6.json` | static `cacheVariables` (finally reviewable) |
| v5 minimal default-module set + optional `ITK_WITH_DCMTK` | `10-itk-v5.json` | static `cacheVariables` |
| v5-vs-v6 gate | shell | selects overlay `inherits` target |
| `ITK_DIR`, `VTK_DIR`, `VkFFT_BACKEND`, nvcc, IGSIO/OpenIGTLink dirs, `binaryDir` | generated overlay | discovered `cacheVariables` |
| all `_patch_*`, PR fetch, two-pass configure, `_stub_remote_examples`, `_overlay_vnl_headers`, `ants_system_args` | shell | not expressible in JSON |

Note on `$env{}` vs `$penv{}`: read-only pixi-env values (FFTW paths, compilers)
use `$env{}`. Values the presets *augment* (e.g. prepending nvcc's dir to `PATH`)
use `$penv{}`. Most "dynamic-looking" values are stable within a pixi env and
resolve via `$env{}` without touching the overlay — only genuinely
forest-computed build-tree paths (VTK/ITK build dirs) land in the overlay.

## Ecosystem-health validation

Each `consumer-<X>.json` carries a build + test + workflow preset chained to the
generated configure overlay:

```jsonc
// consumer-ANTs.json (committed)
"buildPresets":    [{ "name": "forest-ANTs", "configurePreset": "forest-ANTs-local",
                      "jobs": "$env{ITK_FOREST_JOBS}" }],
"testPresets":     [{ "name": "forest-ANTs", "configurePreset": "forest-ANTs-local",
                      "output": { "outputOnFailure": true } }],
"workflowPresets": [{ "name": "forest-ANTs",
                      "steps": [ { "type": "configure", "name": "forest-ANTs-local" },
                                 { "type": "build",     "name": "forest-ANTs" },
                                 { "type": "test",      "name": "forest-ANTs" } ] }]
```

- Unpatched consumers: `cmake --workflow --preset forest-ANTs` runs
  configure→build→test directly (human/IDE-runnable).
- Patched consumers (Slicer, BRAINSTools, plastimatch, …): the wrapper runs
  `patch → cmake --workflow --preset forest-<X>`. Same preset underneath; the
  wrapper only adds the pre-configure source surgery that workflowPresets have no
  hook for.
- `run-matrix.sh` reduces to:
  `for c in consumers: patch_if_needed(c); cmake --workflow --preset forest-$c; assert_artifact(c)`.
  The per-consumer cmake soup leaves the matrix driver too. The artifact assert
  stays — workflow exit code is not artifact proof.

## Honest limitations

1. **No pre-configure hook in workflowPresets.** Patched consumers cannot be a
   pure `cmake --workflow`; the wrapper still front-runs the patch step. The
   preset is human-runnable end-to-end only for unpatched consumers.
2. **Absolute `include` path in the overlay.** Machine-specific, stamped by the
   generator. Acceptable because the overlay is gitignored and machine-local.
3. **Workflow exit code ≠ artifact proof.** The on-disk check is retained.

## Future / deferred

- **`ITK_USE_FFTWD/F=OFF`** (user sidebar, "do when convenient"): flipping FFTW
  off makes ITK fall back to VNL FFT and **removes the `@rpath/libfftw3_*`
  runtime dependency** that currently aborts every ANTs executable (sccan et al.)
  when the conda lib dir is not on an rpath. After this restructure it is a
  one-line reviewable diff in `10-itk-v6.json` with a `$comment`. Cross-ref: the
  2026-07-03 sccan/ANTs dyld investigation.
- **zlib hack** (`ITK_USE_SYSTEM_ZLIB=ON`, temporary as of 2026-07-02): becomes a
  one-line diff + `$comment` in `10-itk-v6.json` instead of a 30-line heredoc
  comment. Revisit once the `DCMTK::ITK::ITKZLIBModule` export bug is resolved.
- **Optional gitignore addition** (not required): if we ever cache discovered
  values to disk, ignore `cmake/presets/*.local.json`. The core design needs no
  `~/.gitignore_global` change.

## Out of scope

- Rewriting the `_patch_*` source-surgery functions.
- Changing `versions.toml` / `config.py` (ref selection is already clean).
- Any change to consumer upstream repos.
