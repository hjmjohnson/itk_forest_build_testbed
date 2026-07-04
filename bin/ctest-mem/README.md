# ctest-mem — memory-aware CTest scheduling

Instrument a CMake/CTest suite so memory-heavy tests no longer pile up and
SIGABRT a RAM-constrained CI runner (the `itkMCI_DSC_case_2_binary`
"Subprocess aborted" on the macos-15 Pixi job, ITK PR #6475 CI).

CTest has the *scheduling* primitives but **cannot measure RSS itself** — so
this kit is two stages: a one-time **measurement pass**, then a generated set
of **scheduling labels** enforced via `RESOURCE_GROUPS` against a RAM budget.

## Stage 1 — measure peak RSS per test

`measure-test-rss.sh` polls the launched process tree via `ps` (macOS + Linux,
no `/usr/bin/time` dependency), records peak summed RSS, and propagates the
child exit code. Use it as a CTest `TEST_LAUNCHER` (CMake ≥ 3.29):

```bash
# In the top-level CMakeLists.txt, after all add_test():
#   include(/abs/path/bin/ctest-mem/attach-launcher.cmake)
cmake -S ITK -B build-prof -DITK_PROFILE_TEST_RSS=ON -DModule_MorphologicalContourInterpolation=ON ...
ctest --test-dir build-prof -j3 -L RUNS_LONG      # or the whole suite
# -> build-prof/ctest-rss.csv  with  name,peakMB,exit  per test
```

Standalone (no CMake change), to spot-check one test:

```bash
RSS_CSV=peaks.csv RSS_NAME=itkMCI_DSC_case_2_binary \
  measure-test-rss.sh ./bin/dscComparison <input.mha> /tmp/o saveImages
```

## Stage 2 — generate scheduling labels + RAM budget

```bash
# Tests over 3 GB -> RESOURCE_GROUPS "mem:<ceil GB>" (default policy=budget)
gen-highmem-props.py build-prof/ctest-rss.csv -o ctest-highmem.cmake
#   include(ctest-highmem.cmake) at the end of the suite's CMakeLists.

# RAM budget the runner exposes as schedulable mem-slots (1 slot == 1 GB):
gen-resource-spec.py --budget-gb 7 -o ci-mem-resources.json
```

Run CI with the budget (note: **pass an absolute path** — ctest `cd`s into the
build dir, so a relative spec path is "File not found"):

```bash
cmake -S ITK -B build -DITK_CTEST_MEMORY_BUDGET=ON ...
ctest --test-dir build -j3 --resource-spec-file "$PWD/ci-mem-resources.json"
```

CTest then guarantees the summed `mem` of concurrently running tests ≤ budget.
Verified: 3×`mem:4` tests against a 7-slot budget under `-j3` serialize
(6.07 s) instead of running in parallel (2.03 s control).

## Policy choice

| Want | Mechanism | Tool flag |
|------|-----------|-----------|
| Cap *aggregate* RAM, still pack small tests around big ones (recommended) | `RESOURCE_GROUPS "mem:N"` + resource-spec file | `--policy budget` (default) |
| A heavy test runs *completely alone* | `RUN_SERIAL ON` | `--policy solo` |
| Soft force-solo without a spec file | `PROCESSORS <large>` | set by hand |

`RESOURCE_GROUPS` is an honor-system scheduling constraint: the test process
need not read `CTEST_RESOURCE_GROUP_*` — declaring the reservation is enough.

## The MCI case specifically

The full-resolution DSC cases measured **~0.7 GB peak each** (663–688 MB),
**not >3 GB** — so a literal ">3 GB ⇒ run alone" rule would *not* flag them.
The macos-15 abort is aggregate memory under `ctest -j3`, so the fix is the
budget approach with ~1 GB reservations: see `itk-mci-memory.cmake` (a gated
drop-in for `Modules/Filtering/MorphologicalContourInterpolation/test/CMakeLists.txt`).

This is independent of PR #6475 — MorphologicalContourInterpolation uses no
eigensystem/eispack code — and belongs in its own commit/PR.
