# ITK forest-build testbed

A [pixi](https://pixi.sh) workspace that builds the **forest** of open-source
ITK consumers — ITK itself plus ANTs, BRAINSTools, Slicer, elastix, c3d, MITK,
SimpleITK, and the ITK remote modules — against one locally built ITK
(`USE_SYSTEM_ITK`), with every compile wrapped by ccache.

**Purpose:** prove that a proposed ITK change — any pull request, branch, tag,
or SHA under test — does not break downstream builds *before* it lands
upstream. The unit of evidence is the **build matrix**: every consumer built
and scored PASS/FAIL by the existence of its artifact on disk, never by pipe
exit codes.

This repo is a **kit** — scripts, pixi config, and docs only. `git clone` it,
then `pixi run checkout` materializes all source trees (git worktrees from
`~/src/<project>` when present, shallow clones otherwise) under the
git-ignored `build_forest/` directory.

## Cheatsheet — copy-paste

### 0. One-time

```bash
git clone git@github.com:hjmjohnson/itk_forest_build_testbed.git
cd itk_forest_build_testbed
pixi run checkout            # materialize all sources into build_forest/ (+ writes build_forest/manifest.toml)
```

### 1. Shell helpers (paste into your shell, from the testbed root)

```bash
export TESTBED="$(pwd)"
forest(){    pixi run bash "$TESTBED/bin/setup-itk-downstream-testbed.sh" "$@"; }  # engine: checkout|build <X>|remotes|manifest|status|list
fmatrix(){   pixi run bash "$TESTBED/bin/run-matrix.sh" "$@"; }                    # full build(+test) sweep, scored by artifact
fbuild(){    pixi run "build-$1"; }                                               # pixi task w/ dependency graph (e.g. fbuild ANTs)
fitk(){      ITK_REF="${1:-origin/main}" pixi run repoint-itk; }                  # point ITK at PR/branch/tag/SHA, then build it
fstatus(){   forest status; }                                                     # ccache stats + checked-out trees
fmani(){     forest manifest; sed -n '1,40p' "$FOREST_DIR/manifest.toml"; }       # (re)write + show this forest's manifest
fver(){      ${EDITOR:-vi} "$TESTBED/versions.toml"; }                            # edit the version source of truth
export FOREST_DIR="$TESTBED/build_forest"
```

### 2. Everyday recipes

```bash
forest build ITK                  # build the ITK under test (root of the forest)
fbuild elastix                    # build one consumer (auto-builds ITK first via pixi deps)
fmatrix                           # full sweep -> PASS/FAIL per target  (RUN_CTEST=0 fmatrix = build-only)
fstatus                           # ccache hit rate + what's checked out
forest list                       # every component + build order
```

### 3. Test an ITK pull request / branch / tag / SHA

```bash
fitk pr/6250                      # GitHub PR (pull/6250/head). Also: fitk upstream/main | fitk v5.4.0 | fitk <sha>
fbuild ANTs                       # rebuild consumers (ccache keeps it fast)
fmatrix                           # prove the whole forest still builds
```

### 4. Pick versions / pins (edit, don't touch shell code)

```bash
fver                              # edit versions.toml: component url/ref/branch + SuperBuild pins + Qt version
forest list                      # confirm the engine sees your edit
# one-off override without editing the file (env wins over versions.toml):
ITK_REF=pr/6250 forest build ITK
BRAINSTools_ANTs_GIT_TAG=<sha> forest build BRAINSTools
```

### 5. Side-by-side forests with shared ccache

Two forests share compiled objects: the 2nd builds at ~100% cache hits and only
recompiles what its ITK ref actually changed (see “How it works” → ccache).

```bash
# Forest B under the testbed (suffixed branches, parallel-safe):
FOREST_REFERENCE_SUFFIX=prB ITK_REF=pr/6250 pixi run repoint-itk
FOREST_REFERENCE_SUFFIX=prB fmatrix          # logs: /tmp/matrix-<name>-prB.log

# Forest B at an arbitrary absolute path (still shares ccache):
BUILD_FOREST_ROOT=/scratch/fb FOREST_REFERENCE_SUFFIX=prB forest checkout ITK
BUILD_FOREST_ROOT=/scratch/fb FOREST_REFERENCE_SUFFIX=prB forest build ITK
```

Matrix logs land in `/tmp/matrix-<target>[-<suffix>].log`; the summary prints
PASS/FAIL/SKIP per target. Each forest carries a `manifest.toml` (repo + resolved
SHA per component) at its root.

## The forest (trees)

Full repository URLs and the floating upstream branch each tree tracks are in
**[CATALOG.md](CATALOG.md)**. Summary:

- **Consumers** (built against the local ITK): ITK, ANTs, BRAINSTools, Slicer
  (+ ExtensionsIndex), elastix, MITK, c3d, SimpleITK.
- **ITK remote modules** (built externally against the local ITK): BioCell,
  Cleaver, HASI, LesionSizingToolkit, PerformanceBenchmarking, RTK, Shape,
  SimpleITKFilters, SkullStrip, SphinxExamples, TractographyTRX, TubeTK,
  Ultrasound, VkFFTBackend — plus heavy (CUDA/Java/wasm) CudaCommon,
  IOOpenSlide, SCIFIO, WebAssemblyInterface under `HEAVY=1`.

Each tree tracks an upstream floating branch (`main`/`master`); the testbed
builds a local worktree off it so the forest follows the moving target an ITK
change must not break.

## How it works

- **One ITK, many consumers.** Consumers point `ITK_DIR` at the local ITK
  build tree; `pixi.toml` `depends-on` encodes the dependency graph, so
  `pixi run build-BRAINSTools` transparently builds ITK → ANTs → BRAINSTools.
- **Versions in one file.** `versions.toml` (root) is the source of truth for
  every component's git URL, ref, and worktree branch, plus the SuperBuild
  dependency pins (Slicer's vendored ITK, BRAINSTools' ANTs, Plastimatch fork)
  and the Slicer Qt version. The engine reads it via `bin/config.py`; edit the
  TOML, not the shell. Env vars still override (`ITK_REF=…`, `BRAINSTools_ANTs_GIT_TAG=…`).
- **Per-forest manifest.** Each forest root gets a human-readable `manifest.toml`
  recording the repo + *resolved SHA* of every checked-out component — what was
  actually built. Regenerate any time with `forest manifest`.
- **ccache everywhere, shared across forests.** All configures pass
  `CMAKE_<LANG>_COMPILER_LAUNCHER=ccache`; Slicer's SuperBuild (which forwards
  compilers but not launchers to its ExternalProjects) gets the ccache
  masquerade compiler instead. `CCACHE_BASEDIR=$FOREST` + `CCACHE_NOHASHDIR`
  rewrite each compile's paths to forest-relative before hashing, so **any two
  forests — even at unrelated absolute `BUILD_FOREST_ROOT` paths — share objects**;
  the 2nd forest hits cache for everything its ITK ref didn't change.
  `-ffile-prefix-map=$FOREST=.` keeps emitted objects byte-reproducible too.
- **Scenario forests.** `FOREST_REFERENCE_SUFFIX=<tag>` routes checkout,
  builds, and logs into `build_forest-<tag>/` with per-forest worktree
  branches, enabling side-by-side comparison of build characteristics across
  ITK branches.

## Doc library

| Task | Doc |
|---|---|
| Fresh-machine setup, env overrides | [docs/bootstrap.md](docs/bootstrap.md) |
| Node-specific paths (Qt6, ccache, compilers) | [docs/config.md](docs/config.md) |
| Testing a change, build matrix, dependency model, scenario forests | [docs/workflow.md](docs/workflow.md) |
| Repo layout and `bin/` scripts | [docs/layout.md](docs/layout.md) |
| Native Windows (MSVC/Ninja/ccache, path rules, MAX_PATH) | [docs/windows.md](docs/windows.md) |
| Slicer on macOS (Qt6/ccache specifics) | [docs/slicer-macos.md](docs/slicer-macos.md) |

`CLAUDE.md` is the entry point for AI-assisted sessions and routes to the same
docs.

## Non-negotiables

- Verify by **artifact**, not exit code (`bin/run-matrix.sh` does this).
- `build_forest*/` is disposable and git-ignored; never commit build output.
- Scripts stay cross-platform (macOS BSD + Linux GNU + native Windows/MSVC).
  Platform differences resolve through `bin/platform.sh`, never a bare `uname`.
