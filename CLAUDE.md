# CLAUDE.md — ITK forest-build testbed

Guidance for Claude Code (and humans). This file is the **entry point**: read it
first, then route to the focused doc in `docs/` for the task at hand.

## What this is

A **pixi workspace** that builds every open-source ITK consumer the pruned
[ITK fork of VXL](https://github.com/InsightSoftwareConsortium/vxl) (branch
`for/itk-vxl-master`, in `~/src/vxl`) must not break — ITK itself, plus ANTs,
BRAINSTools, Slicer, elastix, c3d, MITK, SimpleITK, and the ITK remote modules.
Everything builds against one locally built ITK (`USE_SYSTEM_ITK`), every
compile `ccache`-wrapped, so a single vnl header edit only recompiles the TUs
that include it. The goal: **prove a vnl/vcl pruning or deprecation change does
not break downstream builds before proposing it upstream.**

This directory is a **kit** (scripts + pixi config + docs), not a checkout —
`git clone` then `pixi run checkout` materializes the rest under
`build_forest/`. Remote: `git@github.com:hjmjohnson/itk_forest_build_testbed.git`.

## Doc routing — read the one that matches the task

| If you are about to… | Read |
|---|---|
| Set up the kit on a fresh machine / understand env overrides | [docs/bootstrap.md](docs/bootstrap.md) |
| Set node-specific paths (Qt6, ccache, forest root, compilers) | [docs/config.md](docs/config.md) |
| Test a vnl change, run the build matrix, or read the dependency model | [docs/workflow.md](docs/workflow.md) |
| Understand the repo layout, what's tracked, or the `bin/` scripts | [docs/layout.md](docs/layout.md) |
| Build Slicer (Qt6 / ccache / conda-flag / ITK-branch specifics on macOS) | [docs/slicer-macos.md](docs/slicer-macos.md) |

## Fast path

```bash
pixi run checkout          # materialize source trees into build_forest/
pixi run build-ITK         # build ITK carrying the vendored/synced vnl
# edit ~/src/vxl, then:
pixi run sync-vnl          # overlay vxl into ITK's vendored vnl + rebuild ITK
pixi run build-elastix     # rebuild a consumer (ccache keeps it fast)
pixi run bash bin/run-matrix.sh   # full sweep, scored by artifact
```

## Non-negotiables

- **Verify by artifact, not pipe exit code.** `… | tee/tail` masks failures;
  confirm the binary/library exists on disk. (`bin/run-matrix.sh` does this.)
- **build_forest/ is disposable** and git-ignored (except its README). Never
  commit build output.
- **Cross-platform** (macOS BSD + Linux GNU): `grep -E` not `-P`, avoid `sed -i`
  portability traps, prefer the pixi toolchain (system cmake is often too old
  for Slicer's `>=3.28`).

## Related

- `~/src/vxl/CLAUDE.md` — the vxl fork itself (what is pruned, how to build/test).
