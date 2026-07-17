# CLAUDE.md — ITK ecosystem improvement kit

Guidance for Claude Code (and humans). This file is the **entry point**: read it
first, then route to the focused doc in `docs/` for the task at hand.

## The one purpose

This repo exists to **make ITK and its ecosystem better.** Every script, skill,
rule, and forest here serves that single goal. It supplies **two avenues** toward
it — always know which one you are working in:

- **(a) ITK PR & issue management** — a library of agent skills (`skills/`) plus
  cross-cutting policy (`rules/`) for authoring, reviewing, triaging, and landing
  changes to ITK and its remote modules: the `itk-*` refactor/cleanup skills, the
  `gh-*` PR/issue skills (`gh-triage-pr`, `gh-issue-audit`, `gh-issue-summary`),
  `cdash-build-analysis`, and the `pr-*` / `ingest-*` rules. This avenue improves
  ITK **directly**, one PR or issue at a time.
- **(b) The forest testbed** — an extensive build environment of upstream and
  downstream ITK-related projects that acts as a **sounding board and
  proof-generating environment**: given any ITK ref under test, prove it does not
  break the ecosystem before it lands. This avenue **validates** changes and turns
  genuine breakages into upstream PRs.

The avenues reinforce each other: **(b) produces the evidence that (a)'s PRs are
safe.** State which avenue a task belongs to the same way you state repo + forest.

## Avenue (a): ITK PR & issue management skills

The `skills/` and `rules/` trees are a portable agent-skills library (deployed via
symlinks under `~/.claude/`; canonical source and framework conventions live in the
separate `agent-skills` repo). Skills are self-describing — each `SKILL.md` carries
a v2 contract (triggers, side-effects, determinism, dependencies). Invoke a skill
by its trigger; don't re-derive its steps from memory. Work here targets the
upstream ITK repos, **never** the testbed's build output.

## Avenue (b): the forest testbed — sounding board & proof generator

A **pixi workspace** that builds every open-source ITK consumer — ITK itself,
plus ANTs, BRAINSTools, Slicer, elastix, c3d, MITK, SimpleITK, and the ITK
remote modules — against one locally built ITK (`USE_SYSTEM_ITK`), every compile
`ccache`-wrapped, so a single ITK header change only recompiles the TUs that
include it. The goal: **given any ITK ref under test (a pull request, branch,
tag, or SHA), prove it does not break downstream builds before it lands
upstream.**

Point the ITK worktree at the ref under test with `ITK_REF` (e.g. `pr/6250`,
`upstream/main`, a tag, or a SHA) and `pixi run repoint-itk`, then rebuild the
forest. `manifest.toml` records what the forest **actually** holds -- the
resolved ref, slug, SHA and ITK version -- so the forest's contents are always
knowable regardless of what its directory is called. We assume developer/push privileges on most downstream projects, so a
genuine breakage becomes an upstream PR against that consumer's latest main.

The build environment is reproducible: the conda toolchain (compilers, ninja,
ccache, git, cmake) is version-pinned in `pixi.toml` and frozen exactly by
`pixi.lock`.

This directory is a **kit** (scripts + pixi config + docs), not a checkout —
`git clone` then `pixi run checkout` materializes the rest under
`build_forest/`. Remote: `git@github.com:hjmjohnson/itk_forest_build_testbed.git`.

## ⚠ Always name the REPO and the FOREST you are acting on

This workspace contains **many git repos** and **many parallel build
environments**. A statement of what was done — or will be done — is ambiguous
and easily misread unless it explicitly names *both* coordinates. State them up
front in every plan, summary, commit/PR description, and report.

**1. Which repo?** There are two distinct classes — never conflate them:

- **The kit repo** = *this* directory (`hjmjohnson/itk_forest_build_testbed`).
  Tracks only scripts, pixi config, `docs/`, `utilities/`. Commits/PRs here are
  about the *testbed itself*.
- **Consumer SOURCE repos** checked out *into* a forest — each its own upstream
  project: ITK→`InsightSoftwareConsortium/ITK`, ANTs→`ANTsX/ANTs`,
  BRAINSTools→`BRAINSia/BRAINSTools` (or the `hjmjohnson` fork), Slicer, elastix,
  … (see `CATALOG.md`). PRs here go *upstream*. **Testbed artifacts (analysis,
  reports, perf data, the harness) live ONLY in the kit repo and must never be
  committed into a consumer worktree or attached to a consumer's PR.**

**2. Which forest (sub-environment)?** Each forest is a self-contained build
tree selected by `BUILD_FOREST_ROOT` / `FOREST_REFERENCE_SUFFIX`
(`FOREST_REFERENCE_SUFFIX=foo` ⇒ `build_forest-foo`; no suffix ⇒ `build_forest`).
The suffix is free-form; the **recommended convention** for a ref forest is
`itk-<refslug>` (`FOREST_REFERENCE_SUFFIX=itk-pr6250`), which you type -- nothing
derives or enforces it, and a name can drift from its contents. The record that
cannot drift is `manifest.toml`; `python3 bin/config.py compare <A> <B>` is how
you check which ITK is in which forest. **The same source repo exists in each
forest as a separate worktree on a separate per-forest branch
(`itk-downstream-<suffix>`, etc.) at a possibly different SHA.** "I built ITK"
is meaningless; "I built ITK `pr/6487` in `build_forest-pr6487`" is actionable.

Convention: prefix any consequential statement/command with the coordinates,
e.g. `Repo: ANTsX/ANTs (d2fbf8bd) | Forest: build_forest-pr6487` — and run
forest-scoped commands with the suffix explicit:
`FOREST_REFERENCE_SUFFIX=pr6487 pixi run build-ANTs`.

## Doc routing — read the one that matches the task

| If you are about to… | Read |
|---|---|
| **(a)** Author / review / triage / land an ITK or remote-module PR or issue | the matching `skills/itk-*`, `skills/gh-*` `SKILL.md` + the `rules/pr-*` policies |
| Set up the kit on a fresh machine / understand env overrides | [docs/bootstrap.md](docs/bootstrap.md) |
| Set node-specific paths (Qt6, ccache, forest root, compilers) | [docs/config.md](docs/config.md) |
| Test an ITK PR/branch/tag, run the build matrix, or read the dependency model | [docs/workflow.md](docs/workflow.md) |
| Test a consumer with an in-flight upstream fix while its PR awaits review (the dominant cross-project pattern) — integration branches + per-forest scenario overrides | [docs/integration-branches.md](docs/integration-branches.md) |
| Understand the repo layout, what's tracked, or the `bin/` scripts | [docs/layout.md](docs/layout.md) |
| Build Slicer (Qt6 / ccache / conda-flag / ITK-branch specifics on macOS) | [docs/slicer-macos.md](docs/slicer-macos.md) |
| Pick / build the ITK that Slicer + SlicerExtensions consume — **Slicer's ITK is a per-forest variant of that forest's ITK base; there is no global default** | [docs/slicer-itk-policy.md](docs/slicer-itk-policy.md) |

## Fast path

```bash
pixi run checkout          # materialize source trees into build_forest/
pixi run build-ITK         # build the ITK under test
# point ITK at the ref under test (PR / branch / tag / SHA), then rebuild:
ITK_REF=pr/6250 pixi run repoint-itk   # or ITK_REF=upstream/main, a tag, a SHA
pixi run build-ITK
pixi run build-elastix     # rebuild a consumer (ccache keeps it fast)
pixi run bash bin/run-matrix.sh   # full sweep, scored by artifact

# A dedicated forest for a ref: name it by the convention (you type the suffix).
python3 bin/config.py refslug pr/6250                     # -> pr6250
FOREST_REFERENCE_SUFFIX=itk-pr6250 ITK_REF=pr/6250 pixi run checkout
python3 bin/config.py compare build_forest build_forest-itk-pr6250
```

## Non-negotiables

- **State the repo and forest for every action** (see the ⚠ section above).
  Before committing, building, or reporting, name which repo (kit vs which
  consumer) and which forest/sub-environment. Most misinterpretations here trace
  to an unstated coordinate.
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
