# ITKv6 extension remediation — per-extension actions

Companion to `2026-08-21-itkv6-slicer-status.md`. Covers the **9 extensions
carrying ITKv6 work**: the 6 that pass on ITK 5.4.7 and fail on 6.0.0, plus the
3 whose pre-existing breakage *masks* a v6 regression.

Repo liveness checked 2026-08-21.

## Status at a glance

| extension | state | blocker |
|---|---|---|
| SlicerProstate | **PR open** | needs review |
| DSCMRIAnalysis | **fixed, unmergeable** | upstream repo archived |
| SwissSkullStripper | **PR open since 2026-05-11** | dormant maintainer |
| SlicerElastix | **PR open since 2026-05-11** | dormant maintainer |
| CarreraSlice | **PR open since 2026-06-17** | dormant maintainer |
| MedialSkeleton | needs a PR | none — repo is active |
| PkModeling | needs a PR | repo dead since 2024-04 |
| T1Mapping | needs a PR | **repo archived** |
| Chest_Imaging_Platform | needs work | none — repo active |
| PBNRR | decide: port or retire | abandoned + ITKFEM removed |

Five of nine already have a fix written. **Three of those need nothing but a
maintainer to press merge.**

## Done in this session

### SlicerProstate — PR #60 open

<https://github.com/SlicerProstate/SlicerProstate/pull/60> (draft)

One line: `#include <vnl/algo/vnl_levenberg_marquardt.h>` in
`DWModeling/DWModeling.cxx`. Verified `rc=0` on both ITK 5.4.7 and 6.0.0.

Watch out: merged PR #59 is a *different* ITK6 fix touching the same file
(semicolons after `itkGenericExceptionMacro`). A coarse "was it fixed?" check
reads as yes. It was not.

### DSCMRIAnalysis — fixed, but upstream is archived

Branch `hjmjohnson/DSC_Analysis@comp-itk6-build-fixes`. **`QIICR/DSC_Analysis`
is archived and read-only** (last push 2024-04-23) — GitHub refuses the PR.

Four independent breakages, each revealed by fixing the previous:

1. `vnl/algo/vnl_convolve.h` removed from vendored VXL (ITK #6441) —
   `LMCostFunction::Convolution` reimplemented as a direct truncated linear
   convolution. Equivalence verified against ITK 5.4's `vnl_convolve` over 500
   randomized trials: **max relative deviation 3.075e-14**.
2. `InternalOptimizerType` incomplete at `PkSolver.cxx:99` and
   `itkConcentrationToQuantitativeImageFilter.hxx:477`.
3. `itkGenericExceptionMacro` missing a trailing semicolon at
   `DSCMRIAnalysis.cxx:87`.
4. Dead `itkMultiThreader.h` include at `DSCMRIAnalysis.cxx:7` — **this one
   breaks ITK 5.4 as well**; its only use at line 182 is already commented out.

Builds clean on both ITK 5.4.7 and 6.0.0.

**Action:** ask QIICR to unarchive, or repoint the ExtensionsIndex descriptor
(currently `https://github.com/QIICR/DSC_Analysis.git`, revision `master`).
`Convolution` has no call sites at all, so deleting the helper is a valid
smaller alternative to reimplementing it.

## Merge-only — fix already written by someone else

### SwissSkullStripper — PR #3

<https://github.com/lassoan/SlicerSwissSkullStripper/pull/3>, open since
2026-05-11, non-draft, `MERGEABLE`/`CLEAN`. Replaces the removed 3-argument
`itksys::SystemTools::FindProgramPath` with `FindProgram()`. Only such use in
the tree. `statusCheckRollup` is empty — the repo has no PR workflows, so it is
**not** blocked on CI, only on a dormant maintainer (last push 2024-12-03).

**Action:** merge.

### SlicerElastix — PR #56, and mind which PR you merge

<https://github.com/lassoan/SlicerElastix/pull/56>, open since 2026-05-11,
`MERGEABLE`.

Not a code port — a **stale pin**. `SuperBuild/External_elastix.cmake` pins
`ELASTIX_GIT_TAG "5.1.0"` (2023-01-12). The `expected ';' after 'static_assert'`
failure is upstream elastix issue #1224, fixed by commit `9554422f0` *"COMP: Add
missing semicolons to ITK macro calls"* (2024-08-30).

⚠ That fix is in elastix **5.3.0+ but NOT 5.2.0**. The older PR #53 bumps only
to 5.2.0 and **would not fix this**. PR #56 goes to 5.3.1 and does. Merging the
wrong one looks like a fix and fails.

Also worth fixing while there: the file has a URL typo,
`"$https://github.com/...`.

**Action:** merge #56, close #53.

### CarreraSlice — PR #15 (pre-existing, not v6)

<https://github.com/ikolesov/CarreraSlice/pull/15> *"COMP: Add missing
&lt;iostream&gt; for ITKv6 build"*, open since 2026-06-17, `MERGEABLE`.
PR #14 (sjh26, 2026-04-10) covers the same ground for VTK 9.6.

CarreraSlice fails on **both** ITK arms, so this is pre-existing rot rather than
a v6 regression — but the fix exists and the failure is in the sweep's count.

**Action:** merge one of #14/#15.

## Needs a PR written

### MedialSkeleton — best target

`JolleyLab/SlicerMedialSkeleton`, last push **2026-05-14** — the only affected
repo that is genuinely active. No competing PR; the issue tracker is empty.

`InflateMedialModel/InflateMedialModel.cxx:290`:

    m_pt.set_row(m_tri(i,k), P[k]);
    error: no matching member function for call to 'set_row'

ITKv6's vendored VNL changed the `vnl_matrix::set_row` overload set. Needs the
actual argument types inspected against current VNL — do not guess the
replacement.

**Action:** write the PR. Live maintainer, no competing work; highest chance of
landing.

### PkModeling — same patch as DSCMRIAnalysis probably applies

`QIICR/PkModeling` — not archived, but no code change since 2024-04-23; the
parent `millerjv/PkModeling` is dead since 2018 with open PRs from 2017.

Carries the **identical `PkSolver/` code** and the identical `vnl_convolve`
breakage. The DSCMRIAnalysis patch is the starting point; re-verify rather than
assume the files are byte-identical.

**Action:** port the DSCMRIAnalysis patch, verify, PR to QIICR. Ask whether
QIICR still wants to maintain it.

### T1Mapping — repo archived

`QIICR/T1Mapping` is **archived** (last push 2024-06-12). Fails on 5.4 at *link*
time and on v6 at *compile* time (incomplete `InternalOptimizerType`) — two
different phases, which is why it registers as pre-existing while masking a real
v6 regression.

**Action:** same as DSCMRIAnalysis — unarchive, or repoint/retire the
descriptor. Not worth writing a patch until there is somewhere to send it.

### Chest_Imaging_Platform — two unrelated failures

`acil-bwh/SlicerCIP`, last push 2026-06-26 — active.

- 5.4: `no member named 'cout'` — the standard missing-`<iostream>` case.
- v6: `no member named 'GradientTolerance'` in CIP's own
  `Common/cipNewtonOptimizer.txx`.

`GradientTolerance` is declared on both `itkLBFGSBOptimizer.h` and
`itkLevenbergMarquardtOptimizer.h` in ITK 5.4, but only on LBFGSB in main — a
genuine v6 API removal. Nothing upstream addresses it. Needs a decision about
what the intended replacement is, which is a question for ITK, not only for CIP.

**Action:** fix the `<iostream>` half first (mechanical), then raise the
`GradientTolerance` removal with ITK to establish the migration path before
patching CIP.

## Decide: port or retire

### PBNRR

`aangelos28/PBNRR`, last functional change ~2018; open issue
[#7](https://github.com/aangelos28/PBNRR/issues/7) has had no maintainer
response in four weeks. `SuperBuild/External_ITKFEM.cmake` compiles
`${ITK_SOURCE_DIR}/Modules/Numerics/FEM` directly — a path that no longer
exists.

A workaround exists: [InsightSoftwareConsortium/ITKFEM](https://github.com/InsightSoftwareConsortium/ITKFEM)
(created 2026-06-26) preserves both FEM modules, and ITK main carries
`Modules/Remote/FEM.remote.cmake`, so `-DModule_FEM=ON` is a mechanism. But it
warns FEM is **"UNMAINTAINED and scheduled for REMOVAL in ITK 7"**, so it buys
exactly one release.

**Action:** recommend retirement from the ExtensionsIndex. Porting an abandoned
extension onto a module that is itself scheduled for deletion is work with a
known expiry date.

## Cross-cutting

- **Archived upstreams are the real blocker, not ITK.** Two of nine
  (`DSC_Analysis`, `T1Mapping`) cannot accept a patch at all. The
  ExtensionsIndex still lists them, so they will keep failing every dashboard
  indefinitely. This is an index-hygiene question for the Slicer project.
- **Three PRs are waiting only on a merge** (SwissSkullStripper, SlicerElastix,
  CarreraSlice). Nudging three dormant maintainers is the cheapest available
  reduction in the failure count.
- **`vnl_convolve` removal (ITK #6441) hit two extensions** and there may be
  more outside the ExtensionsIndex. If ITK intends downstream to migrate rather
  than reimplement, a documented replacement in the ITK 6 migration guide would
  be worth more than the individual patches.

## Update 2026-08-21 evening — PR triage across all 43 failures

Checked every failing extension for an open PR that would fix the build if
merged. Repo liveness and PR state verified via `gh`.

### Correction: CarreraSlice — merge #14, not #15

Earlier this file recommended PR #15. That was wrong.

| | [#14](https://github.com/ikolesov/CarreraSlice/pull/14) (sjh26, 2026-04-10) | [#15](https://github.com/ikolesov/CarreraSlice/pull/15) (2026-06-17) |
|---|---|---|
| files | **12** | 3 |
| style | fully `std::`-qualified | `using namespace std;` |
| covers | `deprecated/`, both `tests/`, `KViewerMain`, `fastGrowCut`, `vtkSysInfo` | subset only |

#15 is a strict subset of #14. **Merge #14, close #15.**

### SlicerRT is a force multiplier

Five of the seventeen CONFIG-FAIL extensions declare a dependency on SlicerRT
and die with no compiler error of their own:

- FilmDosimetryAnalysis, GelDosimetryAnalysis, RegistrationQA,
  SegmentRegistration, PathReconstruction

A share of the "37 pre-existing failures" is therefore **one dependency tree,
not 37 independent problems**. SlicerRT is also the most actively maintained
repo in the set (pushed 2026-08-21). Triage it first.

Likewise BoneReconstructionPlanner declares **seven** dependencies and is
cascade-prone.

### Free wins are scarce

Only **CarreraSlice** is curable purely by merging an existing PR. Nine
failing repos have **zero open PRs**, so "none found" is definitive there, not
a judgement call: SlicerAutoscoperM, PerkTutor, SlicerIGSIO, SlicerFreeSurfer,
MatlabBridge, RVXVesselnessFilters, DRRGenerator, MedialSkeleton,
VASSTAlgorithms.

### Rejected candidates — the "same file, wrong bug" trap

Three PRs look like fixes and are not. This is the same trap as SlicerProstate
#59:

| extension | PR | why it does not fix the failure |
|---|---|---|
| SPHARM-PDM | #93, #94 | fix `itkMultiThreader`->`MultiThreaderBase` in `Testing/itkTestMain.h`; the reported failure is `undeclared identifier 'cout'` |
| Chest_Imaging_Platform | #36, #23 | Python module / vtkNRRDWriter rename; touch neither `cout` nor `GradientTolerance` |
| PortPlacement | #2 | `-Winconsistent-missing-override` warning fix, not the missing-slot error |

SPHARM-PDM #93/#94 are real ITK-compat fixes worth merging on their own
merits — they simply do not clear this failure.

### Note on Chest_Imaging_Platform

The failing `GradientTolerance` use lives in `Common/cipNewtonOptimizer.txx`,
which is in the **CIP library repo, not `acil-bwh/SlicerCIP`**. The library
repo could not be located under `acil-bwh`. Fixing this requires identifying
the right upstream first.
