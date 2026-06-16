# CLAUDE.md — ITK forest-build testbed

Guidance for Claude Code (and humans). This file is the **entry point**: read it
first, then route to the focused doc in `docs/` for the task at hand.

## What this is

A **pixi workspace** that builds every open-source ITK consumer — ITK itself,
plus ANTs, BRAINSTools, Slicer, elastix, c3d, MITK, SimpleITK, and the ITK
remote modules — against one locally built ITK (`USE_SYSTEM_ITK`), every compile
`ccache`-wrapped, so a single ITK header change only recompiles the TUs that
include it. The goal: **given any ITK ref under test (a pull request, branch,
tag, or SHA), prove it does not break downstream builds before it lands
upstream.**

Point the ITK worktree at the ref under test with `ITK_REF` (e.g. `pr/6250`,
`upstream/main`, a tag, or a SHA) and `pixi run repoint-itk`, then rebuild the
forest. We assume developer/push privileges on most downstream projects, so a
genuine breakage becomes an upstream PR against that consumer's latest main.

The build environment is reproducible: the conda toolchain (compilers, ninja,
ccache, git, cmake) is version-pinned in `pixi.toml` and frozen exactly by
`pixi.lock`.

This directory is a **kit** (scripts + pixi config + docs), not a checkout —
`git clone` then `pixi run checkout` materializes the rest under
`build_forest/`. Remote: `git@github.com:hjmjohnson/itk_forest_build_testbed.git`.

## Doc routing — read the one that matches the task

| If you are about to… | Read |
|---|---|
| Set up the kit on a fresh machine / understand env overrides | [docs/bootstrap.md](docs/bootstrap.md) |
| Set node-specific paths (Qt6, ccache, forest root, compilers) | [docs/config.md](docs/config.md) |
| Test an ITK PR/branch/tag, run the build matrix, or read the dependency model | [docs/workflow.md](docs/workflow.md) |
| Understand the repo layout, what's tracked, or the `bin/` scripts | [docs/layout.md](docs/layout.md) |
| Build Slicer (Qt6 / ccache / conda-flag / ITK-branch specifics on macOS) | [docs/slicer-macos.md](docs/slicer-macos.md) |
| Pick / build the ITK that Slicer + SlicerExtensions consume | [docs/slicer-itk-policy.md](docs/slicer-itk-policy.md) |

## Fast path

```bash
pixi run checkout          # materialize source trees into build_forest/
pixi run build-ITK         # build the ITK under test
# point ITK at the ref under test (PR / branch / tag / SHA), then rebuild:
ITK_REF=pr/6250 pixi run repoint-itk   # or ITK_REF=upstream/main, a tag, a SHA
pixi run build-ITK
pixi run build-elastix     # rebuild a consumer (ccache keeps it fast)
pixi run bash bin/run-matrix.sh   # full sweep, scored by artifact
```

## Non-negotiables

- **Latest `upstream/main` first; on failure, update before debugging.** Every
  source repo (ITK, ANTs, BRAINSTools, SlicerExecutionModel, …) defaults to its
  `origin/main` / `upstream/main` tip unless a specific commit is requested. On
  the **first build/test failure of a repo, the first action is to fetch and
  checkout its latest main** — the failure is frequently already fixed upstream —
  and only debug/patch if the latest tip still fails. Bump SuperBuild `GIT_TAG`
  pins (e.g. `SuperBuild/External_ANTs.cmake`) to latest main rather than patching
  stale pinned source. Genuine remaining failures become upstream PRs against
  latest main (maintainer has PR access on most of these repos).
- **Verify by artifact, not pipe exit code.** `… | tee/tail` masks failures;
  confirm the binary/library exists on disk. (`bin/run-matrix.sh` does this.)
- **build_forest/ is disposable** and git-ignored (except its README). Never
  commit build output.
- **Cross-platform** (macOS BSD + Linux GNU): `grep -E` not `-P`, avoid `sed -i`
  portability traps, prefer the pixi toolchain (system cmake is often too old
  for Slicer's `>=3.28`).

## Related

- Each consumer's upstream repo + the floating branch it tracks: see `CATALOG.md`.
