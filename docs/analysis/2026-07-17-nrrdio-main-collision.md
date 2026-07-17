# Cross-project analysis: a `main()` in a library silently deleted 17 downstream tests

**Date:** 2026-07-17
**Found by:** ITK downstream build testbed (`hjmjohnson/itk_forest_build_testbed`)
**Projects spanned:** NrrdIO → ITK → BRAINSTools (Teem: ruled out)
**Status:** root-caused; upstream fix pending

## One-line summary

A demo program with `main()` was added to NrrdIO's library source list; ITK vendors
that list; the resulting `libITKNrrdIO` exports `main()`; downstream GoogleTest
executables silently link the demo's `main()` instead of `gtest_main`'s, so
`gtest_discover_tests` registers **zero** tests and the suite shrinks with a green build.

## Why it is interesting

The failure is **silent and cross-project**. No error, no warning, at any layer:

- ITK builds clean.
- BRAINSTools builds clean; every GTest executable links and runs.
- ctest reports `396 tests passed` — which reads as success.
- The only symptom is that the number used to be 413.

Nothing in any single project's CI could see it: ITK's CI does not build BRAINSTools'
GTest suite; BRAINSTools' CI (on ITKv5) does not exhibit it. It is visible only where
both are built together against a *changed* ITK — i.e. exactly what a downstream
testbed is for.

## Discovery path (how the testbed surfaced it)

1. Built BRAINSTools `767ba471` (BRAINSia main) twice: once against ITK `release-5.4`
   (5.4.6), once against ITK `main` (6.0.0). Same BRAINSTools commit, same ANTs
   (`ebeb304a` via `USE_SYSTEM_ANTs=ON` on both), same ctest invocation. **ITK was the
   only variable.**
2. Test counts differed: **413 (v5) vs 396 (v6)**. A pass/fail diff would have shown
   nothing — the 17 were *absent*, not failing. Distinguishing ABSENT from FAILED was
   what made the finding possible.
3. The missing 17 were all `Suite.TestName` form → GoogleTest, not CLI tests.
   16 in `ImageCalculator`, 1 in `BRAINSABC`.
4. The GTest **binaries existed on both sides** and both *ran*. But on v6:

   ```
   $ ImageCalculatorUtilsGTest --gtest_list_tests
   (from Teem 2.0.0, early 2026)
   demoIO: trouble reading "--gtest_list_tests":
   [nrrd] nrrdLoad: fopen("--gtest_list_tests","rb") failed
   ```

   The "GTest binary" was Teem's `demoIO`. On v5 the same binary correctly prints
   `Running main() from googletest/src/gtest_main.cc`.
5. `nm` on the ITK libraries:

   ```
   itk-main (v6):        libITKNrrdIO-6.0.a:sampleIO.c.o: T _main     <-- library defines main()
   itk-release-5.4 (v5): libITKNrrdIO-5.4.a: (none)
   ```

## Root cause

`sampleIO.c` is **NrrdIO's usage demo** — it defines `demoIO()` and `main()`:

```c
sampleIO.c:29   demoIO(const char *fnin, const char *fnout) {
sampleIO.c:77   main(int argc, const char **argv) {
sampleIO.c:83     fprintf(stderr, "(from Teem %s, %s)\n", ...);
```

It is **not** part of Teem (`find ~/src/teem -iname '*sampleIO*'` → 0 matches); it is
NrrdIO-specific. Teem is not implicated.

It entered NrrdIO's library sources here:

```
~/src/nrrdio/CMakeLists.txt:81      sampleIO.c      (inside set(nrrdio_SRCS ...))
git blame -> 1279d6bc  Hans Johnson  2025-10-22
             "ENH: Adding missing files from the cmake build list"
```

That commit added four files. **Three were correct** (`encodingZRL.c`, `preamble.c`,
`subset.c` are genuine library sources); `sampleIO.c` was not. There is **no
`add_executable`** for it anywhere in NrrdIO — it exists only as a library source.

### The enabling condition: two source lists, one fact

NrrdIO carries the same fact twice, and they disagree:

| list | entries | `sampleIO.c`? |
|---|---|---|
| `NrrdIO_Srcs.txt` (canonical, Teem-derived) | 41 | **no** |
| `CMakeLists.txt` `nrrdio_SRCS` | 43 | **yes** |

Delta = `preamble.c` (legitimately NrrdIO-only) + `sampleIO.c` (the bug). Because the
CMake list is maintained by hand rather than derived from the canonical list, a
reconciliation against a directory listing could not distinguish demo from library.
Had `nrrdio_SRCS` been generated from `NrrdIO_Srcs.txt` (+ an explicit NrrdIO-only
addendum), the mistake would have been unrepresentable.

## Propagation

```
NrrdIO/CMakeLists.txt  nrrdio_SRCS += sampleIO.c        (2025-10-22, 1279d6bc)
        |  vendored into ITK (0-gen.sh regenerates ITK's NrrdIO from this repo)
        v
ITK  Modules/ThirdParty/NrrdIO/src/NrrdIO/CMakeLists.txt:88   sampleIO.c
        |  (v5's copy predates the change and does NOT list it)
        v
libITKNrrdIO-6.0.a exports  _main  (from sampleIO.c.o)
        |  any executable linking ITK's NrrdIO + gtest_main now has TWO main()s
        v
BRAINSTools  ImageCalculatorUtilsGTest / BlendImageFilterGTest  == demoIO
        |  gtest_discover_tests runs the binary, gets Teem's banner, parses 0 tests
        v
17 unit tests silently unregistered on ITKv6.  ctest reports "396 passed".  Green.
```

## Is it the extraction scripts, or ITK? (asked 2026-07-17)

Neither, exactly — and this is the useful part of the story.

- **The scripts are not implicated.** `0-gen.sh`/`mangle.py`/`pre-GNUmakefile` regenerate
  *headers* (`NrrdIO.h`, `itk_NrrdIO_mangle.h.in`). They never touch `CMakeLists.txt`.
- **The scripts already had it right.** `NrrdIO_Srcs.txt`, which the extraction produces,
  lists 41 Teem sources and correctly omits the demo.
- **ITK is not the origin.** ITK's vendored source list is byte-identical to NrrdIO's
  (43 sources, both with `sampleIO.c`); ITK's file is a thin ITK-specific wrapper
  (6 ITK-isms) around the same hand-maintained list. ITK inherited the defect.
- **The defect is that the list was maintained twice**: once generated
  (`NrrdIO_Srcs.txt`, correct) and once by hand (`nrrdio_SRCS`, wrong). The hand copy
  is the one that builds. A manual reconciliation against a directory listing cannot
  distinguish a demo from a library source — both are `.c` files in the same directory.

The originating commit was *right about 3 of the 4 files it added*
(`encodingZRL.c`, `preamble.c`, `subset.c` are genuine sources). Only `sampleIO.c` was
wrong, and nothing in the system could have said so.

## Fix applied (NrrdIO, `main`, dc2d8d2)

`nrrdio_SRCS` is now **derived from `NrrdIO_Srcs.txt`**, with NrrdIO-only sources named
explicitly in a separate `nrrdio_EXTRA_SRCS` (`preamble.c` today). Deriving the list
*is* the fix: `sampleIO.c` disappears because it was never in the generated list, not
because someone remembered to exclude it. Plus:

- `CMAKE_CONFIGURE_DEPENDS` on `NrrdIO_Srcs.txt` → re-running the extraction
  re-configures automatically instead of leaving a stale list.
- A `FATAL_ERROR` if any listed source is missing → a stale list becomes a
  configure-time error naming the file, not a link-time mystery.

Verified: configure 0, build 0, `libNrrdIO.a` `main()` definitions **1 → 0**, and the
derived list is exactly `old − {sampleIO.c}` (43 → 42, nothing else changed). The
existence guard was confirmed to fire by injecting a bogus entry.

## Remaining fixes (to be decided)

| # | where | change | notes |
|---|---|---|---|
| A | NrrdIO | remove `sampleIO.c` from `nrrdio_SRCS` | minimal, correct, one line. Does not fix ITK until ITK re-vendors. |
| B | NrrdIO | build `sampleIO.c` as an optional demo executable | preserves the demo's purpose; it currently builds as *nothing*. |
| C | NrrdIO | derive `nrrdio_SRCS` from `NrrdIO_Srcs.txt` + explicit addendum | removes the dual-list enabling condition; makes the class of bug unrepresentable. |
| D | ITK | drop `sampleIO.c` from the vendored list | unblocks ITKv6 downstreams now, without waiting on a re-vendor. |
| E | ITK or NrrdIO | CI guard: assert the built library exports no `main` (`nm`) | catches the whole class, cheaply. |

Fix D is the ASAP unblock; A (+B) is the upstream correctness fix; C removes the
enabling condition; E prevents recurrence.

## Separate finding, same run — root-caused 2026-07-17

```
BRAINSFitTest_MIHAffineRotationMasks            ITK 5.4.6: 10/10 PASS   ITK 6.0.0: 0/10 PASS
BRAINSFitTest_MIHScaleSkewVersorRotationMasks   ITK 5.4.6: 10/10 PASS   ITK 6.0.0: 0/10 PASS
```

**Not an ITK defect.** ITK PR #6569 (merged 2026-07-16) corrected two coupled bugs in
`JointHistogramMutualInformationImageToImageMetricv4` — the metric `--costMetric MIH`
selects. BRAINSTools' baselines were generated in **2018** against the buggy metric, so
they encode a wrong answer. The tests fail by disagreeing with a stale snapshot; the
action is regenerating the baselines, not changing ITK.

Full analysis: **`2026-07-17-jhmi-metric-correction.md`**.

The two findings are instructive as a pair — same run, opposite polarity:

| | this doc (NrrdIO) | JHMI |
|---|---|---|
| suite says | **green** | **red** |
| reality | 17 tests silently absent | upstream fix working as intended |
| action | fix the library | regenerate the baseline |

Neither "passed" nor "failed" is interpretable without knowing what the test measures.

## Verification log

| claim | evidence |
|---|---|
| v6 NrrdIO defines `main` | `nm -g -o libITKNrrdIO-6.0.a` → `sampleIO.c.o: T _main` |
| v5 does not | same command → 0 matches |
| the binary is really `demoIO` | `--gtest_list_tests` → `demoIO: trouble reading ...` + Teem banner |
| v5 binary is really GTest | `Running main() from googletest/src/gtest_main.cc` |
| `sampleIO.c` not from Teem | `find ~/src/teem -iname '*sampleIO*'` → 0 |
| both lists disagree | `comm` of `NrrdIO_Srcs.txt` vs `nrrdio_SRCS` → `preamble.c`, `sampleIO.c` |
| 17 = 16 + 1 | `ImageCalculator` 33→17, `BRAINSABC` 2→1 |
| not a flake | 10 runs/side on the 2 MIH tests: 10/10 vs 0/10 |
