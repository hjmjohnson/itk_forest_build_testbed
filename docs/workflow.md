# Workflow — testing an ITK change

The whole point: **prove an ITK change (any pull request, branch, tag, or SHA)
does not break downstream builds before it lands upstream.**

```bash
# 1. Point the ITK worktree at the ref under test. `checkout` honors ITK_REF,
#    so a fresh forest lands on the ref in one step; `repoint-itk` moves the
#    ITK worktree of a forest that is already checked out. Both take the same
#    ref forms and resolve them identically:
ITK_REF=pr/6250          pixi run checkout      # GitHub PR  (pull/6250/head)
ITK_REF=upstream/main    pixi run checkout      # a remote branch
ITK_REF=v5.4.0           pixi run checkout      # a tag
ITK_REF=<sha>            pixi run checkout      # a commit
ITK_REF=pr/6251          pixi run repoint-itk   # move an existing forest's ITK
# 2. Build ITK, then the consumers you care about (ccache keeps it fast):
pixi run build-ITK
pixi run build-elastix
pixi run build-Slicer
# 3. Full sweep, scored by artifact:
pixi run bash bin/run-matrix.sh
```

Prefer a guided flow? `pixi run tui` walks the same steps interactively
(forest → ITK ref → projects → tests) and saves each run's exact command
plan to `<forest>/logs/tui-plan-<timestamp>.sh`.

## Selecting the ITK ref

`ITK_REF` accepts any of: a local branch, a tag, a SHA, a remote ref
(`<remote>/<branch>` — its remote is fetched first), or the GitHub PR shorthand
`pr/NNNN` (fetched as `pull/NNNN/head`). PRs are fetched from `origin` by
default; override with `ITK_PR_REMOTE`. Both `checkout` and `repoint-itk` share
one ref-resolution implementation: they reset the ITK worktree and check the ref
out onto the local branch `itk-downstream` (suffixed per forest). Unset,
`ITK_REF` falls back to ITK's `versions.toml` default and no request is
recorded. A ref that cannot be checked out is fatal — it never falls through to
a forest silently holding a different ref.

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
FOREST_REFERENCE_SUFFIX=itk-pr6250 ITK_REF=pr/6250 pixi run checkout
FOREST_REFERENCE_SUFFIX=itk-pr6250 pixi run bash bin/run-matrix.sh   # logs: <forest>/logs/matrix-<name>-itk-pr6250.log
```

`itk-<refslug>` is a **recommended convention you type**, not a rule: the suffix
is free-form, nothing derives it from `ITK_REF`, and nothing refuses a name that
disagrees with the forest's contents. Get the conventional slug with
`python3 bin/config.py refslug pr/6250` (-> `pr6250`).

Since a name is only a promise, the safety net is the record: each forest's
`manifest.toml` holds the **resolved** ITK ref, slug, SHA and version, and

```bash
python3 bin/config.py compare build_forest-itk-release-5.4 build_forest-itk-pr6250
```

reports the `## forest` identity and per-component `ref`/`slug`/`sha` deltas —
that is how you check which ITK is in which forest before trusting a result.

Worktree branch names are suffixed (`itk-downstream-pr6250`) since git allows a
branch in only one worktree. Cross-forest ccache hits are enabled by
`CCACHE_BASEDIR=<testbed root>` + `CCACHE_NOHASHDIR=true` (set by the build
engine): identical TUs hash identically regardless of which forest compiled
them, so the second forest only recompiles objects its ITK ref actually changes.
