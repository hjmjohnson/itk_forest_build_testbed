# itk-init-over-assign: design

Date: 2026-10-27. Status: draft for review.
Repo: kit (`hjmjohnson/itk_forest_build_testbed`). Forest: any; the skill
runs against one consumer worktree inside a named forest.

## Intent

Hans prefers initialization to assignment and wants variables declared in
the smallest scope that needs them. PR BRAINSia/BRAINSTools#645 did this
for BRAINSTools by hand-driving fifteen agents; it is an alpha run kept
for ideation and comparison, and it will be discarded once the skills
here have been run on BRAINSTools `main`. Its diff is the parity
reference for stage coverage, not a source of code. This design turns that
work into a repeatable, unattended skill set that runs on one repo in the
forest (ITK, ANTs, BRAINSTools, elastix, and the remote modules) and
leaves a branch of ordered commits for a human to review.

The reviewer's cognitive load is the thing being optimized. One commit
holds one kind of transform across the whole repo, so the reviewer learns
the pattern once and then scans. Commits are not split by module.

## Goals

1. A master skill, `itk-init-over-assign`, that runs every stage on one
   repo with no stops and no questions, then partitions the result into
   ordered commits by transform kind.
2. Each stage is a sub-skill (new or refined) that can also run alone.
3. A const/constexpr promotion pass follows every stage that enables one,
   as its own commit, so the reviewer sees the promotion next to the
   initialization that allowed it.
4. Every commit compiles with no new warning (the `itk-compile-gate.sh`
   contract), and the branch tip passes a full build and ctest.
5. Comments travel with the code they describe. A stranded or deleted
   comment is a stage failure, not a style nit.
6. Existing skills are refined so the ecosystem improves, rather than
   bypassed by a parallel implementation.

## Non-goals

- Cross-repo work. One repo per run; another repo is another run.
- Opening PRs. The skill never runs `gh pr create`; it reports and stops.
- Behavior changes. Any transform that could change observable behavior
  is skipped and listed, never attempted.
- Member layout, types, const on members, and names stay as they are
  (adding a default member initializer is allowed; reordering is not).
- Qt, Python, CMake, and third-party trees (`Modules/ThirdParty`,
  `Utilities/`, vendored code, `build/`).

## Anti-goals

The run has failed, whatever the build says, if:

- a comment was dropped or left orphaned from its declaration;
- a value that must survive between loop iterations was moved into the
  loop;
- a costly or side-effecting construction (ITK `New()`, file streams,
  reused buffers) was moved into a loop;
- a brace initialization narrowed a value or selected an
  `initializer_list` constructor the original code did not;
- an initializer list was written out of member declaration order;
- a declaration crossed a `goto`, a `switch` case label, a `try` boundary
  it was read after, or an `#if`;
- a header that no translation unit in the build includes was changed
  without a syntax check against at least one including TU.

## Stages

Stages are an ordered list in the master skill. Adding a kind means adding
a list entry and the sub-skill that implements it. The initial list:

| # | Kind | Sub-skill | Engine |
|---|------|-----------|--------|
| 1 | Member init | `itk-member-init` (new) | clang-tidy `cppcoreguidelines-prefer-member-initializer`, then `modernize-use-default-member-init` |
| 2 | Local declare-then-init | `itk-declare-then-init` (refined) | existing Python finder, classes `assign`, `elem_diff`, `elem_zero`, plus the four new classes below |
| 2c | const/constexpr after 2 | `itk-const-promote` (new) | clang-tidy `misc-const-correctness` on locals; constexpr by rule (below) |
| 3 | Container list init | `itk-container-list-init` (new) | clang-query match of `push_back`/`operator[]` runs after a default construction; rewrite to brace list |
| 3c | const after 3 | `itk-const-promote` | same |
| 4 | ITK helpers | `itk-sizetype-filled` (refined), `itk-allocate-initialized` (refined), `fillbuffer-over-iterate` pattern | `Fill(k)` to `T::Filled(k)` / `MakeFilled<T>(k)`, `Allocate(true)` to `AllocateInitialized()`, iterator fill loops to `FillBuffer` |
| 4c | constexpr after 4 | `itk-const-promote` | `Filled(k)` with a literal `k` becomes `constexpr` |
| 5 | Narrow scope | `itk-narrow-scope` (new) | move a declaration to its first use, into the block, branch, loop body, or `for`/`if` init-statement that uses it |

Stage 2 gains four classes, each a separate rule with its own detector,
fixtures, and skip reasons, so the finder stays one-class-per-rule:

| Class | Before | After |
|-------|--------|-------|
| `sized_ctor` | `std::vector<T> v; v.resize(n);` (also `set_size`, `SetSize`) | `std::vector<T> v(n);` |
| `stream_open` | `std::ofstream f; f.open(x);` | `std::ofstream f(x);` |
| `bool_branch` | `bool b = false; if (c) { b = true; }` with no `else` and no other write | `const bool b = c;` |
| `placeholder` | `T p = nullptr; p = f();` or `int n = 0; n = f();` with no read between | `T p = f();` |

Stage 4 owns the `Fill` family. When the master runs stage 2 it passes
`--classes assign,elem_diff,elem_zero` so the finder's `fill_*`,
`elem_same`, and `setsize_fill` classes are left for stage 4. Canonical
spellings follow ITK's `Documentation/AI/code-review-lessons.md` section
10 (single-expression initialization): `constexpr T v{};` or `T v{};` for
a zero fill; `constexpr auto v = T::Filled(k);` or `auto v = T::Filled(k);`
when `T` provides `Filled` (every `FixedArray`-derived type: Size, Index,
Offset, Vector, Point, and Spacing); `auto v = itk::MakeFilled<T>(k);`
only for a type without `Filled`. `Filled` is preferred over `MakeFilled`
wherever both apply. Smart-pointer members get no `{}` initializer
(`compiler-cautions.md` 1a).

Stage 5 runs last because narrowing a scope after initialization is a
pure move with no initializer rewrite, so its diff is the easiest to
review and depends on all earlier stages being settled.

Stage 2c through 4c share one sub-skill. There is no const pass after
stage 1: `misc-const-correctness` analyzes locals only, and a `const` data
member deletes copy assignment, which is a behavior change. The constexpr rule: a promoted variable becomes `constexpr`
only when its initializer is a literal, a `constexpr` function call on
literals, or `T::Filled(literal)`; everything else that
`misc-const-correctness` reports becomes `const`. `static` locals are
left alone.

## How a run proceeds

The master skill:

1. Resolves the repo and forest from arguments or the cwd, prints the
   coordinate line (`Repo: ANTsX/ANTs (sha) | Forest: build_forest-itk-main`),
   and refuses to run on a dirty tree or on `main`.
2. Confirms the worktree HEAD equals the consumer's floating upstream
   branch tip from `CATALOG.md` (fetched first). If the worktree is ahead
   (a forest integration commit) or behind, it refuses and names the
   `pixi run` refresh command; it does not rebuild on the human's behalf.
   Then creates branch `style-init-over-assign-<YYYYMMDD>` from that HEAD,
   so the branch is pushable as a PR and the ninja graph matches it.
3. Locates the ninja graph: a `compile_commands.json` at depth 2 or
   less under the repo's `build/` in that forest, preferring the directory
   whose name starts with the repo name (BRAINSTools has both
   `build/BRAINSTools-Release-EPRelease-build/` and
   `build/SlicerExecutionModel-Release-build/`), and uses
   that directory for the gate, the full build, and ctest. Confirms it
   exists for the repo in that forest and that `pixi run clang-tidy --version` reports the same
   series as the forest compiler (19.1 today). The tidy tools come from
   the kit's pixi environment (`clang-tools`, added 2026-10-27), never
   from Homebrew.
4. Runs every stage in order against the working tree. A stage applies
   its transform to all files, runs `itk-compile-gate.sh --changed` on
   the touched TUs plus including TUs for each touched header, capped at
   eight per header (the first TU from each distinct top-level directory
   that includes it, then the rest by path order), and
   writes a site manifest (JSON: file, line range, kind, class, and any
   `skipped` reason). Nothing is committed yet.
5. After the last stage, partitions the whole diff into commits by
   manifest kind, in stage order. A hunk that two manifests claim goes to
   the later stage, so earlier commits stay self-contained.
6. For each commit, runs the comment check (below), `clang-format` on the
   touched files, and `itk-compile-gate.sh` on the touched TUs. A failure
   reverts that hunk, records it in the skip list, and continues.
7. Runs `pre-commit run --all-files`, a full ninja build of the repo in
   that forest, and `ctest` with the forest's `run-matrix.sh` include
   list and timeouts. The criterion is no new failure against a baseline
   ctest run on the base SHA. The baseline is cached in the kit at
   `.devlocal/init-over-assign/baselines/<repo>-<sha>.json` and is run
   once per base SHA, before the stages start.
8. Writes the report (below) and stops. It never pushes and never opens
   a PR.

The "apply everything, then partition" order is deliberate. Committing
per stage as the run goes would force every later stage to be rebased
over earlier commits whenever a hunk is reverted in step 6; partitioning
once at the end makes the revert local.

### Partitioning the diff

Each sub-skill's manifest records the line ranges it rewrote. The
partitioner walks `git diff -U0` hunks, assigns each hunk to the stage
whose manifest covers it, and builds one commit per stage with
`git apply --cached` of the selected hunks. A hunk no manifest covers
(for example clang-format spill) is attached to the stage that touched
the nearest line above it. The per-stage const/constexpr commit is built
the same way from `itk-const-promote`'s manifest.

Commit messages: `STYLE: <kind sentence> across <repo short name>`, with
a body listing the count of sites and the count skipped, and no
reference to prior code. Examples:

```
STYLE: Initialize members in constructor initializer lists
STYLE: Initialize locals at declaration instead of assigning
STYLE: Make initialized locals const where never mutated
STYLE: Replace push_back and index sequences with list initialization
STYLE: Use Filled, MakeFilled, and AllocateInitialized helpers
STYLE: Declare variables in the narrowest scope that uses them
```

### Comment check

For every hunk in every commit: each removed line that is a comment (line
or block, including trailing comments on a code line) must reappear as an
added line within the same hunk, or in a hunk of the same commit whose
added code contains the identifier the comment's original neighbor
declared. Doxygen blocks that precede a member or function move with it.
`TODO`, `FIXME`, `NOTE`, and `HACK` lines are matched by exact text, and
a miss is a hard failure for that hunk (reverted, listed).

### Skip list

Every sub-skill classifies the sites it declines to transform using the
same reason vocabulary (`loop-carried`, `costly-construct`, `try-read-
after`, `preprocessor`, `goto-or-case`, `narrowing`, `init-list-ctor`,
`static-local`, `order-violation`, `no-including-tu`, `comment-stranded`,
`gate-failed`, `itk-version`). The report groups the skip list by reason with file and
line, so a human can choose to hand-fix the ones worth it.

### Report

`<kit>/.devlocal/init-over-assign/<repo>-<YYYYMMDD_HHMM>.md`, with:

- the coordinate line, branch name, and tip SHA;
- one row per commit: SHA, kind, files, sites, and gate result;
- which commits touch disjoint files from every other commit (candidates
  for separate PRs, if the human wants them);
- the skip list by reason;
- the full-build and ctest results, with any new warning quoted;
- a PR body draft at `<kit>/.devlocal/pr-bodies/<repo>-init-over-assign.md`
  in the `pr-message-format` shape, for the human to post.

Report and manifests live in the kit's `.devlocal/`, never in the
consumer worktree.

## Changes to existing skills

- `itk-declare-then-init`: add `--apply --manifest <path>` so the finder
  writes its edits and a manifest without committing; add the skip-reason
  vocabulary; stop assuming the `Modules/**` layout (ANTs has `Examples/`
  and `ImageRegistration/`; BRAINSTools has per-tool directories), taking
  paths from `compile_commands.json` instead.
- `itk-sizetype-filled`: same `--apply --manifest` mode; no branch or PR
  creation when invoked by the master; read clang-query from the pixi env.
- `itk-allocate-initialized`: same; drop the network requirement.
- `itk-mechanical-cleanup` patterns `in-class-member-init` and
  `fillbuffer-over-iterate`: `transform.sh --apply --manifest <path>`.
- `itk-clang-tidy-refactor`: unchanged in v1. The two tidy stages
  (`itk-member-init`, `itk-const-promote`) call `run-clang-tidy` from the
  pixi environment directly; folding a manifest mode into the
  `~/scripts/dev/cxx14_updates` wrappers is deferred.
- `itk-compile-gate.sh`: accept headers, resolving them to including TUs
  through `compile_commands.json` (the `check_syntax.py` helper from the
  #645 session does this and can be folded in).
- `itk-incremental-refactor-loop`: unchanged; it remains the interactive,
  stop-between-classes driver. Its SKILL.md gains a pointer to the
  master for the unattended case.

## New skills

- `itk-init-over-assign` (master): the run described above; argument
  `<repo> [--forest <suffix>] [--stages 1,2,...] [--dry-run]`.
- `itk-member-init`: clang-tidy stage 1 with the order-violation guard
  (an initializer list that would be out of declaration order is
  rewritten in declaration order, and if any initializer depends on a
  later member it is skipped with `order-violation`).
- `itk-const-promote`: `misc-const-correctness` with
  `AnalyzeValues`, `AnalyzeReferences`, and `WarnPointersAsValues` set
  for locals; constexpr by the rule above.
- `itk-container-list-init`: clang-query matcher plus Python rewrite, the
  same guards as #645 (no narrowing, no `initializer_list` surprise,
  element count preserved and verified by re-parsing the result).
- `itk-narrow-scope`: Python over clang-query `varDecl` plus use sites;
  moves only when every use is inside one nested block and the
  declaration has no side effects. Moving into a `for`/`if`
  init-statement is allowed. Moving into a loop body is allowed only
  when the type is trivially constructible and the value is not read
  before it is written on any iteration; otherwise skipped with
  `loop-carried` or `costly-construct`.

All skills follow the v2 frontmatter contract and the `<scope>-<verb>`
naming rule; `agent-skills doctor` must pass before the kit commit.

## Verification

- Unit tests under `skills/<skill>/tests/` for each transformer, run by
  `pixi run test`, with before/after fixture pairs for every guard in the
  anti-goals list (one fixture per skip reason).
- The partitioner has a fixture repo with a known diff and expected
  commit assignment.
- The comment check has fixtures for a moved Doxygen block, a trailing
  comment, and a stranded `TODO`.
- End-to-end: a run on BRAINSTools (`main`, ninja graph at
  `build/BRAINSTools-Release-EPRelease-build/`) must produce a green
  branch before the master is declared done; its result replaces PR #645.
  ITK, ANTs, and the others follow as separate runs the human triggers.

## Open questions settled as my calls

- No const pass after the member-init stage (reviewer check, item 1).
- Stage 4 owns the `Fill` family; stage 2 runs with the fill classes off.
- Narrow scope may enter init-statements and trivially constructed loop
  locals, never a loop-carried or costly one.
- The branch base is the catalog's floating upstream tip; the skill
  refuses a worktree that differs rather than rebuilding.
- ctest passes when there is no new failure against a cached baseline on
  the base SHA.
- The header gate is capped at eight including TUs per header.
- BRAINSTools is the end-to-end target; v1 checks one forest.
- Decided by Hans (2026-10-27): the kinds #645 covered beyond the stage
  table become separate rules (the four stage 2 classes above); spelling
  follows ITK's AI docs, with `Filled` preferred over `MakeFilled`.
- Stage 5 (narrow scope) runs last, after all initialization stages.
- const promotion is a separate commit after each stage, not folded in.
- Hunks claimed by two stages go to the later stage.
- The branch name carries the date, not the stage list.
- The skill refuses a dirty tree rather than stashing.

## Out of scope for the first version

- A second forest. One run checks one forest; the ITK-helper stage reads
  the ITK version from the forest's `ITKConfig.cmake` and skips
  `Filled`/`MakeFilled` sites with `itk-version` when ITK is older than
  the helper.

- Windows. The kit's `platform.sh` rules apply, but the first version is
  tested on macOS and Linux only.
- Parallel stages. Stages run sequentially; within a stage, files may be
  processed in parallel where the engine is clang-tidy (`run-clang-tidy
  -j`).
- A `-fix` for anything clang-tidy itself cannot fix; those sites are
  skipped with the tidy diagnostic quoted in the skip list.
