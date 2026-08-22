# ITKv6 in Slicer — status as of 2026-08-21

Prepared in response to Dženan Zukić's question of 2026-08-20:
*"What is the current status of updating ITK to v6 in Slicer?"*

**Forest:** `build_forest-itk-main`, reset to pure upstream tips on 2026-08-21.
**Kit repo:** `hjmjohnson/itk_forest_build_testbed`.

## Short answer

Slicer `main` still consumes **ITK 5.4.7**. The v6 migration was scoped in
May 2026, demonstrated working, and has been **dormant since 2026-05-30** —
blocked on one unowned upstream decision, not on a pile of broken code.

Slicer *core* is in good shape. The cost is concentrated in (a) one ITK patch
that has never landed upstream, and (b) a long tail of third-party extensions,
most of which is pre-existing rot rather than ITKv6 damage.

## What each project is pinned to

| Project | Slicer `main` uses | Current upstream |
|---|---|---|
| ITK | 5.4.7 (`d458a374`) | 6.0.0 (`9f127d9231`) |
| BRAINSTools | `ced799ad` (2025-11-10) | `db7baa6c` (2026-08-21) |
| ANTs (via BRAINSTools) | `2a25b6b0` | `d92f933e` |
| ExtensionsIndex | — | `0c0792c`, 255 descriptors |

Slicer's `SuperBuild/External_ITK.cmake` pins `Slicer/ITK` at tag
`slicer-v5.4.7-2026-07-21-4c49df9`. Slicer's most recent ITK-touching commit is
*"COMP: Update ITK to 5.4.7"* (2026-07-25). The `Slicer/ITK` fork has **no v6
branch at all**; the only v6-facing branch is the experimental
`slicer-upstream-main-namespace-2026-05-10`, which SuperBuild does not
reference.

## The one real blocker

Slicer needs ITK's **customizable-namespace** patch
(`COMP: Add support for customizing ITK namespace`). Verified today against
current ITK main: still not upstream.

    git log --oneline upstream/main \
        --grep='^COMP: Add support for customizing ITK namespace'
    # -> 0 results

Because it is not upstream, every Slicer-ITKv6 build must carry it privately —
which is why a `Slicer/ITK` fork branch has to exist per ITK revision at all.
Landing it in ITK main removes that requirement permanently.

Discourse #7758 ends on 2026-05-12 with Dženan asking @jcfr what remains to
integrate this commit into ITK main. **That question was never answered.** It is
the critical path.

Related and unmerged: `Slicer/ITK` PR #14 (blowekamp, `ITK_LOAD_SYMBOL` autoload
namespace, open since 2026-01-13). Dženan suggested folding it into the same
work.

## Also worth stating plainly

**ITK 6.0.0 is not released.** Latest release is v5.4.7 (2026-08-10); v6 exists
only as `v6.0b02` (2026-03-25). The "ITK 6.0 Release Candidate 1" milestone is
open with 4 outstanding items and no due date. Slicer cannot ship on v6 before
ITK ships v6, so the near-term goal is a *green dashboard*, not a release.

## Prior evidence (Slicer issue #9149, 2026-05-10)

Slicer core built and ran against ITK upstream main with
`ITK_FUTURE_LEGACY_REMOVE=ON`:

- **663/675 ctest passing (98%)**, Ubuntu 24.04, gcc 13.3, Qt 6.8.2
- 2 Slicer source fixes needed — both missing
  `<itkImageRegionIteratorWithIndex.h>` includes; **landed** as PR #9219
  (2026-06-11)
- 6 new test failures vs the Qt5 baseline
- Extensions: **152/249 packaged (61%)**

## Open upstream items

| Item | State | Note |
|---|---|---|
| Slicer #9149 | open, dormant since 2026-05-30 | tracking issue |
| Slicer #9316 | **draft**, opened 2026-07-27 | BRAINSTools pin bump |
| Slicer #8193 | open since 2025-01-28 | remove deprecated Jacobian methods |
| Slicer/ITK #14 | open since 2026-01-13 | autoload namespace |
| Discourse #7758 | dormant since 2026-05-12 | unanswered question to @jcfr |

PR #9316 is a one-line, low-risk pin bump that unblocks `DWIConvert` compiling
against ITK main. It pins `aca0edc1` (2026-07-23); current BRAINSTools main is
four weeks newer. **It can land independently of the whole v6 question** and
should.

## The extension tail — and what kind of breakage it actually is

The 2026-07-22 sweep built all 253 ExtensionsIndex descriptors in both an
ITK 5.4 forest and an ITK main forest:

| forest | pass | fail |
|---|---|---|
| ITK 5.4 (control) | 218 | 35 |
| ITK main | 211 | 42 |

**35 fail in BOTH.** That is pre-existing upstream rot, not ITKv6 damage — the
single most important number for setting expectations. Zero extensions fail
only on 5.4. The ITKv6-attributable delta is **5 extensions**.

Re-verified 2026-08-21: all five are **still unfixed** at their default-branch
HEAD.

| Extension | Cause | Verdict |
|---|---|---|
| SwissSkullStripper | `itksys::SystemTools::FindProgramPath` removed | fix written, PR #3 open |
| MedialSkeleton | `vnl_matrix::set_row` overload changed | best PR target — active repo |
| SlicerProstate | incomplete `InternalOptimizerType` | one-line include fix |
| PkModeling | `vnl/algo/vnl_convolve.h` dropped | abandoned (dead since 2017) |
| PBNRR | ITKFEM module removed | abandoned + architecturally blocked |

Only two are worth new effort. SwissSkullStripper merely needs its existing
PR #3 merged.

### Three of the five are the same phenomenon: include-pruning

`SlicerProstate` and `PkModeling` both fail because ITKv6 stopped *transitively*
providing a VNL header. Verified in the ITK tree today:

    # itkLevenbergMarquardtOptimizer.h, release-5.4
    #include "vnl/algo/vnl_levenberg_marquardt.h"

    # ... in main it is replaced by a forward declaration
    class vnl_levenberg_marquardt;
    using InternalOptimizerType = vnl_levenberg_marquardt;   // still exported

The alias survives, so the ITK header compiles fine. The type is merely
*incomplete* at any downstream call site that touches a member — which is why
`DWModeling.cxx:787` fails on `vnlOptimizer->set_f_tolerance(1e-4f)`.

This shape deserves attention out of proportion to its size:

- the error appears in **downstream** code, far from the ITK change;
- it hits only consumers who relied on the transitive include, so ITK's own CI
  is green;
- the fix is one `#include` in the consumer, not an ITK revert.

Provenance, stated plainly: the forward declaration was introduced by ITK commit
`7ec9ffd452 ENH: Eigen-backed Levenberg-Marquardt for
itk::LevenbergMarquardtOptimizer` — our own work. This is a deliberate,
defensible ITKv6 change whose downstream cost was simply invisible until
something built the ecosystem against it. That is exactly what this testbed
exists to make visible.

## Method, and one measurement trap worth recording

Every component was moved to its true upstream tip before building, and the
forest was cleaned of an unrelated in-flight experiment
(`enh-tier-unsupported-math-6620`) that had been sitting on the ITK, ANTs and
BRAINSTools worktrees. Without that reset the report would have measured
"ITK main plus an unmerged PR".

Resetting the *sources* was not sufficient. The first ANTs build after the reset
failed to link:

    Undefined symbols for architecture arm64:
      "itk::unsupported::Math::detail::RectangularSVDEigen<double>(...)"

Zero ANTs source files referenced that symbol, yet `libantsUtilities.a` still
carried **18** references to it, and `libBRAINSCommonLib.a` carried **35**.
The archives were stale output from the experiment; the compilers had never
been asked to rebuild them.

Two corrections were applied before collecting any numbers:

1. `ANTs/build` and `BRAINSTools/build` were deleted outright rather than
   incrementally rebuilt.
2. `system_headers` was dropped from `CCACHE_SLOPPINESS` for the sweep. With it
   set, ccache may reuse an object compiled against *older ITK headers* — which
   is precisely the invalidation this exercise depends on detecting.

Both are instances of the standing rule that a build is verified by its
artifacts, not by an exit code. `nm` on the archive is the only reliable check
when an environment change invalidates objects without changing any command
line.

## New finding: ITK main breaks `find_package(ITK)` for UNIX consumers

Found 2026-08-21 while building ANTs against ITK `9f127d9231`. **Not previously
reported** — no matching ITK issue or PR exists.

ANTs fails at **configure** time, before a single translation unit compiles:

    The link interface of target "ITK::ITKNrrdIO" contains:
        Threads::Threads
      but the target was not found.
    CMake Generate step failed.

`Modules/ThirdParty/NrrdIO/src/CMakeLists.txt` calls
`find_package(Threads REQUIRED)` and appends `Threads::Threads` to
`ITKNrrdIO`'s exported link interface. `ITKConfig.cmake` never resolves that
dependency in the consumer's scope — ITK's package config has no
`find_dependency` mechanism at all.

- Introduced **2026-07-24** by PR #6695, *"BUG: Locale-independent float
  parsing and printing in NRRD/DICOM IO"*.
- **`main` only** — `release-5.4` is unaffected.
- Merged two days *after* the 2026-07-22 sweep, which is why the previous run
  did not see it.

**Why ITK's own CI stays green:** ITK's build has `Threads` in scope, and any
consumer that independently calls `find_package(Threads)` is unaffected. Only an
external consumer that does not — ANTs — trips it.

Minimal reproducer, verified in both directions:

    find_package(ITK REQUIRED COMPONENTS ITKIONRRD)
    include(${ITK_USE_FILE})
    add_executable(probe m.cxx)
    target_link_libraries(probe PRIVATE ${ITK_LIBRARIES})

| ITK state | configure |
|---|---|
| main as-is | rc=1, Generate step failed |
| main + 7-line fix | rc=0 |

A probe **without** a target linking ITK passes even on broken ITK — CMake never
has to resolve the interface. Any reproducer for this bug must link something.

Fix on branch `comp-itkconfig-find-dependency-threads`: `find_dependency(Threads)`
guarded by `if(UNIX)`, before the `ITKTargets.cmake` include. This is worth
landing independently of the Slicer v6 question — it currently blocks anyone
building against ITK main.

### Consequence for this sweep

Two separate ITKs had to be patched, and forgetting the second would have
burned hours:

1. the forest's own ITK (`itk-downstream-itk-main`), consumed by ANTs,
   BRAINSTools, elastix, …;
2. **Slicer's** ITK, built by Slicer's SuperBuild from the per-forest variant
   `slicer-v6.0.0-2026-08-21-9f127d92314`.

BRAINSTools' first failure was pure cascade: it wanted
`ANTs/build/Examples/libantsUtilities.a`, which never existed because ANTs
never configured. Not an independent finding, and it would have been reported as
one by any check that only read exit codes.

## Build results — ITK 6.0.0 arm (2026-08-21)

Forest `build_forest-itk-main`. Scored by artifact via
`bin/slicer-extension-status.sh`, **not** by SuperBuild exit code — the
SuperBuild discards extension failures (`Ignoring result '255'`) and always
reports success.

| stage | result |
|---|---|
| ITK 6.0.0 `9f127d9231` (+ Threads fix) | pass, 10m38s |
| ANTs `d92f933e` | pass, 202 executables |
| BRAINSTools `db7baa6c` | pass |
| **Slicer core** | **pass** |
| Extensions | **210 pass / 43 FAIL** of 253 |

**Slicer core builds against current ITK main.** That is the headline: the core
application is not the obstacle.

The 43 failures split 24 BUILD-FAIL / 19 CONFIG-FAIL. All five previously
known regressions appear (MedialSkeleton, PkModeling, SlicerProstate,
SwissSkullStripper, PBNRR), consistent with none having been fixed upstream.

The 43 is **not** the ITKv6 cost. A control sweep on ITK 5.4.7 with every
other component pinned to identical SHAs is required to separate genuine v6
regressions from pre-existing rot; the prior baseline had 35 extensions failing
on both. See the control section below.

## A cache-corruption incident that invalidates naive sweeps

Three consecutive ANTs "failures" during this run were **not** ITK findings.
Worth recording, because any of them would have been reported as a downstream
regression by a process that trusted exit codes.

| apparent failure | actual cause |
|---|---|
| ANTs undefined symbols (run 1) | stale archives left by an unrelated experiment |
| BRAINSTools missing `libantsUtilities.a` | cascade of the above |
| ANTs undefined symbols (runs 2-3) | **ccache serving objects built against a different ITK** |

The cache held entries created while `CCACHE_SLOPPINESS` included
`system_headers`. That flag **excludes ITK's headers from the cache key**, so
those entries are keyed as though ITK never changed, and ccache keeps serving
them against a different ITK. For a testbed whose entire purpose is detecting
the downstream effect of ITK header changes, this is the one setting that can
silently invalidate every result.

Three properties made it hard to diagnose, and each defeated an initial
hypothesis:

1. **Purging the build tree does not help.** The poison lives in `~/.ccache`;
   a pristine build tree repopulates itself with stale objects.
2. **Changing the sloppiness setting does not retroactively invalidate.**
   Entries written under the old policy persist and keep matching.
3. **It heals one TU at a time, which fakes a fix.** Every isolated single-TU
   test came back clean and cache-miss, because testing it rewrote that entry.
   Two separate "not reproducible" conclusions were drawn while 29 archives sat
   poisoned.

The decisive evidence was that **all 101 archives were produced by one ninja
run, yet only 29 were poisoned.** No environmental cause can produce that
split — only per-entry cache state.

Remediation needs both halves; neither works alone:

- `CCACHE_RECACHE=1` alone — no effect on TUs ninja considers up to date, since
  the compiler is never invoked;
- deleting objects alone — ninja recompiles and ccache re-serves the poison.

Delete the poisoned archives **and** their objects, then rebuild with
`CCACHE_RECACHE=1`. Verified 29 -> 2 -> 0, ending with 202 ANTs executables
present and zero `unsupported` symbols.

Fixed in `pixi.toml` (drops `system_headers`), which prevents new poisoning but
does not clean what already exists.

**Implication:** any earlier sweep that reused this cache across ITK revisions
may carry the same corruption. The 2026-07-22 numbers cannot be retroactively
certified. An `nm`-based poison check belongs in `bin/run-matrix.sh` so a sweep
fails loudly rather than producing plausible, wrong results.

## The answer: 6 real ITKv6 regressions, not 43

Control sweep, ITK 5.4.7, every other component pinned to the identical SHA as
the v6 arm. Verified after the fact that Slicer's ITK EP really was on
`slicer-v5.4.7-...` (5.4.7) in the control and `slicer-v6.0.0-...` (6.0.0) in
the v6 arm, with BRAINSTools `db7baa6c` in both.

| arm | pass | fail |
|---|---|---|
| ITK 5.4.7 (control) | 216 | 37 |
| ITK 6.0.0 | 210 | 43 |

43 = **6 ITKv6 regressions** + **37 pre-existing**. Zero extensions are fixed
by v6.

### The 6 (fail on 6.0, pass on 5.4)

| extension | cause | upstream state |
|---|---|---|
| SwissSkullStripper | `itksys::SystemTools::FindProgramPath` removed | fix written, PR #3 open since 2026-05-11 |
| MedialSkeleton | `vnl_matrix::set_row` overload changed | repo actively maintained -- best PR target |
| SlicerProstate | incomplete `LevenbergMarquardtOptimizer::InternalOptimizerType` | one-line include; maintainer merges same-day |
| PkModeling | `vnl/algo/vnl_convolve.h` no longer transitively provided | abandoned (no code change in 4 yr) |
| PBNRR | ITKFEM module removed | abandoned + architecturally blocked |
| **SlicerElastix** | elastix `static_assert` syntax under v6 | **new -- not in the 2026-07-22 baseline** |

### 3 more are masked by pre-existing breakage

These fail in **both** arms, but for **different reasons** -- their pre-existing
rot hides a genuine v6 regression that surfaces the moment the rot is fixed.

| extension | 5.4 failure | v6 failure |
|---|---|---|
| DSCMRIAnalysis | `itkMultiThreader.h` not found | `vnl/algo/vnl_convolve.h` not found |
| T1Mapping | link failure | incomplete `InternalOptimizerType` |
| Chest_Imaging_Platform | `no member named 'cout'` | `no member named 'GradientTolerance'` |

`GradientTolerance` is declared on both `itkLBFGSBOptimizer.h` and
`itkLevenbergMarquardtOptimizer.h` in 5.4, but only on LBFGSB in main -- a real
v6 API removal.

**So the true extension workload is 9, not 6 and not 43.** A rule of "fails in
both arms => pre-existing" would have silently discarded three real regressions.

### What signature-reading got wrong

Before the control ran, error signatures suggested DSCMRIAnalysis, T1Mapping and
IntensitySegmenter were regressions and that SlicerElastix was not. The control
reversed three of those four:

| extension | predicted from signature | measured |
|---|---|---|
| DSCMRIAnalysis | regression | pre-existing (**but masks** one) |
| T1Mapping | regression | pre-existing (**but masks** one) |
| IntensitySegmenter | regression | pre-existing -- same cause in both arms |
| SlicerElastix | not ITK | **genuine regression** |

The five-extension `cout`/`cerr` cluster looked like a sixth include-pruning
casualty; it fails identically on 5.4 and is unrelated to ITK. Signature
reading generates hypotheses. Only the control measures.

## Recommended sequence

1. **Land ITK #6776** (`Threads::Threads`). Blocks every UNIX consumer of ITK
   main today, independent of Slicer. Draft, awaiting review; see the PR for the
   #1502/#1503 precedent that argues for removing the leak instead.
2. **Add an external-consumer CI job to ITK** -- `find_package(ITK)` **and link
   a target**, from a standalone project. Six lines of CMake; would have caught
   #6776 on the PR, and covers the latent `DCMTK::*` / `GTest::gtest` /
   `MPI::MPI_C` leaks of the same class.
3. **Answer the question in Discourse #7758** -- what remains to land the
   customizable-namespace commit in ITK main. Unanswered since 2026-05-12 and it
   is the critical path: while it stays out, every Slicer-ITKv6 build must carry
   it privately, which is the only reason a `Slicer/ITK` v6 fork branch needs to
   exist at all.
4. **Land Slicer #9316** (BRAINSTools pin). Draft since 2026-07-27, one line,
   unblocks `DWIConvert` against ITK main. Independent of v6.
5. **Extensions, in cost order:** merge SwissSkullStripper PR #3 (already
   written); PR SlicerProstate (one include) and MedialSkeleton (live
   maintainer); triage SlicerElastix; decide whether PkModeling and PBNRR are
   worth porting or should be retired -- both abandoned, and PBNRR needs a
   removed ITK module.

Slicer core needs **no source changes**. Its only accommodation on the
integration branch is a one-line dependency-pin bump.

## Caveats

- macOS arm64 only. Linux and Windows are unmeasured.
- Build-only. No extension test suites were run; Slicer's own ctest was not run
  in this sweep (issue #9149 reported 663/675 on Linux in May).
- 19 of the 37 pre-existing failures are CONFIG-FAILs with no compiler error;
  several are likely dependency cascades rather than independent breakage, and
  were not individually triaged.
- SlicerANTs fails on a git stash operation, not a compile -- testbed plumbing,
  counted in neither arm's ITK cost.
- The ccache corruption described above means earlier sweeps of this forest
  cannot be retroactively certified. Both arms of *this* comparison were audited
  with `nm` and are clean.
