# Coverage parity check for CTest-to-GoogleTest conversions

Proves that a batch of conversions does not lower line coverage of library
code, per test and in aggregate. Uses LLVM source-based coverage and assumes
Xcode's `llvm-cov` and `llvm-profdata`; change the `xc`/`XC` path for other
toolchains.

## Steps

```bash
export COVERAGE_MODULES_FILE=$PWD/modules.txt   # one ITK module name per line
export ITK_DATA_STORE=/path/to/ExternalData/store   # optional
C=<skill-dir>/coverage

# 1. Two coverage builds: the base and the batch (merge the branches first)
$C/configure_coverage_build.sh <base-src> <base-build>
$C/configure_coverage_build.sh <batch-src> <batch-build>
ninja -C <base-build>; ninja -C <base-build> ITKData   # same for the batch

# 2. Aggregate: three runs per side; compare steady-state runs
for r in 1 2 3; do
  $C/run_coverage_tests.sh <base-build> base_r$r 6
  $C/export_per_driver.sh <base-build> base_r$r
done   # and the same for the batch
python3 $C/compare_coverage.py base_r2/per_driver,base_r3/per_driver <base-src> \
  batch_r1/per_driver,batch_r2/per_driver,batch_r3/per_driver <batch-src> report.md

# 3. Per test: old CTest alone vs its GoogleTest alone
python3 $C/per_test_coverage.py inventory.json <base-build> <base-src> \
  <batch-build> <batch-src> per_test 4
python3 $C/classify_per_test.py per_test/per_test_coverage.json
python3 $C/repeat_pairs.py inventory.json <base-build> <base-src> \
  <batch-build> <batch-src> repeat 3 <flagged tests...>
```

`inventory.json` is a list of `{"legacy_test", "old_file", "new_file",
"stream", "module_dir", "commits"}`, one per conversion.

## Effects the method separates (each found in the 2026-10 beta run)

- **Per-driver export.** Header templates compile differently in each
  driver. Exporting all drivers together dropped coverage for over 40,000
  functions, so `export_per_driver.sh` merges only each driver's own raw
  profiles (mapped by `map_profile_signatures.sh`).
- **Legacy driver startup.** `main` calls
  `ProcessArgumentsAndRegisterRequiredFactories` before dispatching to any
  test. `per_test_coverage.py` measures it by running the driver with an
  unknown test name and subtracts it. TestKernel is excluded as test
  infrastructure.
- **Run-to-run variation.** Threaded and randomized tests vary. The
  aggregate is compared over several runs per side, and per-test residuals
  are rerun with `repeat_pairs.py` (`rerun_variability.sh` reruns a module's
  tests to show a line varies on unchanged code).
- **First run on a fresh tree.** Directory creation and file-exists
  branches run once. Compare steady-state runs, not the first build's run.

## Explained per-test residuals (`classify_per_test.py`)

- `factory-environment`: the `ObjectFactoryBase` loop over registered
  factories. The legacy driver registers IO and FFT factories; GoogleTest
  drivers register none.
- `exception-printing`: originals printed caught exceptions;
  `EXPECT_THROW` does not, so `ExceptionObject::Print` and its chain go
  unreached. The throwing code is still covered.
- `check-helper`: `itk::Math`, `SmartPointer`, and `Index` helpers the
  original used for its checks, replaced by the equivalent `EXPECT_*`.

Anything else is unexplained until a repeat run shows it varies, or the
conversion is fixed.
