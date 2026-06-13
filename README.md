# ITK forest-build testbed

A [pixi](https://pixi.sh) workspace that builds the **forest** of open-source
ITK consumers — ITK itself plus ANTs, BRAINSTools, Slicer, elastix, c3d, MITK,
SimpleITK, and the ITK remote modules — against one locally built ITK
(`USE_SYSTEM_ITK`), with every compile wrapped by ccache.

**Purpose:** prove that a proposed ITK change (a vnl/vcl pruning, an FFT
backend swap, any branch under test) does not break downstream builds *before*
proposing it upstream. The unit of evidence is the **build matrix**: every
consumer built and scored PASS/FAIL by the existence of its artifact on disk,
never by pipe exit codes.

This repo is a **kit** — scripts, pixi config, and docs only. `git clone` it,
then `pixi run checkout` materializes all source trees (git worktrees from
`~/src/<project>` when present, shallow clones otherwise) under the
git-ignored `build_forest/` directory.

## Tutorial (terse)

```bash
git clone git@github.com:hjmjohnson/itk_forest_build_testbed.git && cd itk_forest_build_testbed
pixi run checkout                          # materialize all sources into build_forest/
pixi run build-ITK                         # build ITK (the root of the forest)
pixi run build-elastix                     # build one consumer (auto-builds ITK first)
pixi run bash bin/run-matrix.sh            # full sweep -> PASS/FAIL per consumer

# Test an ITK branch:
ITK_REF=hjmjohnson/pocketfft-backend pixi run repoint-itk
pixi run bash bin/run-matrix.sh

# Test a local vxl/vnl edit (edit ~/src/vxl first):
pixi run sync-vnl                          # overlay vxl into ITK's vendored vnl
pixi run build-ITK && pixi run build-ANTs

# A/B scenarios — independent parallel forest, same ccache:
export FOREST_REFERENCE_SUFFIX=itkv6_main  # -> build_forest-itkv6_main/
pixi run checkout
ITK_REF=upstream/main pixi run repoint-itk
pixi run bash bin/run-matrix.sh            # logs: /tmp/matrix-<name>-itkv6_main.log

pixi run status                            # ccache stats + what's checked out
```

Matrix logs land in `/tmp/matrix-<target>[-<suffix>].log`; the summary prints
PASS/FAIL/SKIP per target.

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
builds a local worktree off it so the forest follows the moving target a
vnl/vcl change must not break.

## How it works

- **One ITK, many consumers.** Consumers point `ITK_DIR` at the local ITK
  build tree; `pixi.toml` `depends-on` encodes the dependency graph, so
  `pixi run build-BRAINSTools` transparently builds ITK → ANTs → BRAINSTools.
- **ccache everywhere.** All configures pass
  `CMAKE_<LANG>_COMPILER_LAUNCHER=ccache`; Slicer's SuperBuild (which forwards
  compilers but not launchers to its ExternalProjects) gets the ccache
  masquerade compiler instead. `CCACHE_BASEDIR` + `CCACHE_NOHASHDIR` make
  cache hits path-independent, so parallel `build_forest-<suffix>` scenario
  forests only recompile what their branch actually changes.
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
| Slicer on macOS (Qt6/ccache specifics) | [docs/slicer-macos.md](docs/slicer-macos.md) |

`CLAUDE.md` is the entry point for AI-assisted sessions and routes to the same
docs.

## Non-negotiables

- Verify by **artifact**, not exit code (`bin/run-matrix.sh` does this).
- `build_forest*/` is disposable and git-ignored; never commit build output.
- Scripts stay cross-platform (macOS BSD + Linux GNU).
