# Workflow — testing an ITK change

The whole point: **prove an ITK change (any pull request, branch, tag, or SHA)
does not break downstream builds before it lands upstream.**

```bash
# 1. Point the ITK worktree at the ref under test:
ITK_REF=pr/6250          pixi run repoint-itk   # GitHub PR  (pull/6250/head)
ITK_REF=upstream/main    pixi run repoint-itk   # a remote branch
ITK_REF=v5.4.0           pixi run repoint-itk   # a tag
ITK_REF=<sha>            pixi run repoint-itk   # a commit
# 2. Build ITK, then the consumers you care about (ccache keeps it fast):
pixi run build-ITK
pixi run build-elastix
pixi run build-Slicer
# 3. Full sweep, scored by artifact:
pixi run bash bin/run-matrix.sh
```

## Selecting the ITK ref

`ITK_REF` accepts any of: a local branch, a tag, a SHA, a remote ref
(`<remote>/<branch>` — its remote is fetched first), or the GitHub PR shorthand
`pr/NNNN` (fetched as `pull/NNNN/head`). PRs are fetched from `origin` by
default; override with `ITK_PR_REMOTE`. `repoint-itk` resets the ITK worktree
and checks the ref out onto the local branch `itk-downstream`.

## Dependency model

The task graph is in `pixi.toml` via `depends-on`, so building any consumer
transparently (re)builds its prerequisites:

```
ITK  ->  ANTs  ->  BRAINSTools
ITK  ->  Slicer  ->  SlicerExtensions
ITK  ->  {elastix, c3d, MITK, SimpleITK}
ITK  ->  build-remotes (TubeTK, RTK, Ultrasound, BioCell, ...)

SlicerRT, SlicerIGSIO, SlicerANTs
```

- `pixi run list` — every known project + category.
- `pixi run status` — ccache stats, TESTBED/FOREST, checked-out projects.
- `pixi run repoint-itk` — move the ITK worktree to a new `ITK_REF`, then build.

> Forcing a rebuild: `pixi run build-<X>` is subject to pixi's task cache and
> may no-op if it believes nothing changed. To force a consumer rebuild (e.g.
> after `repoint-itk`), invoke the engine directly:
> `pixi run bash ./bin/setup-itk-downstream-testbed.sh build <X>`.

Each consumer is checked out on a per-project patch branch (`ants-itk-downstream`,
`slicer-itk-downstream`, …) that carries any fixes needed to build it against
current ITK. We assume push privileges on most consumers, so when a build fails
for a reason that is *not* the ITK ref under test, the fix becomes an upstream PR
against that consumer's latest main.

## Verify by artifact, never by pipe exit code

`bin/run-matrix.sh` scores each project by checking the **build artifact exists**
(e.g. `ITK-build/lib/libITKCommon-6.0.a`, `elastix-build/bin/elastix`), because
`pixi run X | tee/tail` returns the *tail's* exit status and masks failures.
Apply the same discipline by hand: confirm the binary/library on disk; don't
trust a green pipeline.

`bin/run-matrix.sh` deliberately excludes a set of known, pre-existing failures
unrelated to the ITK ref under test (documented in `docs/DEFERRED-FAILURES.md`) —
re-include a target only after its cause is fixed.

## Side-by-side scenario forests

Set `FOREST_REFERENCE_SUFFIX=<tag>` to route everything (checkout, builds,
matrix, logs) into `build_forest-<tag>` instead of `build_forest`, so two ITK
refs can be compared side by side:

```bash
FOREST_REFERENCE_SUFFIX=pr6250 pixi run checkout
FOREST_REFERENCE_SUFFIX=pr6250 ITK_REF=pr/6250 pixi run repoint-itk
FOREST_REFERENCE_SUFFIX=pr6250 pixi run bash bin/run-matrix.sh   # logs: /tmp/matrix-<name>-pr6250.log
```

Worktree branch names are suffixed (`itk-downstream-pr6250`) since git allows a
branch in only one worktree. Cross-forest ccache hits are enabled by
`CCACHE_BASEDIR=<testbed root>` + `CCACHE_NOHASHDIR=true` (set by the build
engine): identical TUs hash identically regardless of which forest compiled
them, so the second forest only recompiles objects its ITK ref actually changes.
