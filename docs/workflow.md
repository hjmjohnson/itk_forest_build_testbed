# Workflow — testing a vnl change

The whole point: **prove a vnl/vcl pruning or deprecation change does not break
downstream builds before proposing it upstream.**

```bash
# 1. Edit the numerics source:   ~/src/vxl  (vcl/, core/vnl/, v3p/, config/)
# 2. Overlay it into ITK's vendored copy and rebuild ITK:
pixi run sync-vnl          # rsync vxl -> ITK/Modules/ThirdParty/VNL/src/vxl, then build-ITK
# 3. Rebuild the consumers you care about (ccache makes unaffected TUs instant):
pixi run build-elastix
pixi run build-Slicer
# 4. Full sweep, scored by artifact:
pixi run bash bin/run-matrix.sh
```

`sync-vnl` rsyncs `vcl/`, `core/`, `v3p/` with `--delete` (so removals are
reflected) and `config/` additively (ITK-added probe files survive).

## Dependency model

The task graph is in `pixi.toml` via `depends-on`, so building any consumer
transparently (re)builds its prerequisites:

```
ITK  ->  ANTs  ->  BRAINSTools
ITK  ->  Slicer  ->  SlicerExtensions
ITK  ->  {elastix, c3d, MITK, SimpleITK}
ITK  ->  build-remotes (TubeTK, RTK, Ultrasound, BioCell, ...)
```

- `pixi run list` — every known project + category.
- `pixi run status` — ccache stats, TESTBED/FOREST, checked-out projects.
- `pixi run repoint-itk` — move the ITK worktree to a new `ITK_REF`
  (e.g. latest `upstream/main` or a proposed PR ref), then `sync-vnl` + build.

## Verify by artifact, never by pipe exit code

`bin/run-matrix.sh` scores each project by checking the **build artifact exists**
(e.g. `ITK-build/lib/libITKCommon-6.0.a`, `elastix-build/bin/elastix`), because
`pixi run X | tee/tail` returns the *tail's* exit status and masks failures.
Apply the same discipline by hand: confirm the binary/library on disk; don't
trust a green pipeline.

`bin/run-matrix.sh` deliberately excludes a set of known non-vxl failures
(documented inline in the script) — re-include a target only after its
non-vxl cause is fixed.

## ITK ref and the vendored-vnl pin

`ITK_REF` selects the ITK branch the testbed builds. It must vendor
`for/itk-vxl-master` with a matching VNL CMake wrapper (`vcl` is
INTERFACE/header-only); `sync-vnl` then overlays your working-tree vxl on top.
Regenerate the upstream ITK re-vendor PR branch with
`bin/revendor-vnl-into-itk.sh <isc-vxl-tag>` (prerequisite: the vxl snapshot is
already a tag on `InsightSoftwareConsortium/vxl`).
