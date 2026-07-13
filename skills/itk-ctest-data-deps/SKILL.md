---
name: itk-ctest-data-deps
version: 1.0.0
purpose: 'Fix CTest test data dependency issues in ITK/CMake projects: missing DEPENDS on Uncompress/ExternalData tests, unconditional add_dependencies on optional targets (InstallReferenceAtlas), and parallel test ordering races.'
description: >-
  Fix CTest test data dependency issues in ITK/CMake projects: missing DEPENDS
  on Uncompress/ExternalData tests, unconditional add_dependencies on optional
  targets (InstallReferenceAtlas), and parallel test ordering races. Use when
  tests fail with "file not found" or "directory does not exist" due to missing
  test data. Trigger on: "test data missing", "directory not found in test",
  "Uncompress dependency", "InstallReferenceAtlas", "ExternalData tarball",
  "parallel test race", "test depends on data".
triggers:
  - itk-ctest-data-deps
  - /itk-ctest-data-deps
user_invocable: true
cmd: false
argument_hint: null
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: false
    writes_to_repo_paths: []
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: false
    network_required: false
    git_required: false
    user_confirmation_required: false
  determinism: hybrid
  cache:
    has_cache: false
    cache_root:
    schema_version: 0
    rebuildable: true
  derivation:
    has_ai_derived_layer: false
    derivation_version: 0
dependencies:
  skills: []
  external_tools: []
  python_packages: []
  scripts: []
deployment:
  tier: always
  target_projects: []
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK/CTest Test Data Dependency Fixes

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-ctest-data-deps — Fix CTest test data dependency issues (no arguments)

Usage:
  /itk-ctest-data-deps          Scan and fix missing DEPENDS, add_dependencies,
                                and parallel test ordering races in cwd project

Patterns: Uncompress deps, InstallReferenceAtlas, ExternalData races.
```

Test data dependency problems are a common source of non-deterministic test
failures in ITK-based projects using `ExternalData_add_test`.

## Pattern 1 — Missing DEPENDS on Uncompress test

**Symptom:** A test fails with "input directory not found" when run in parallel
(`--schedule-random` or `-j N`). The test passes when run alone.

**Root cause:** The test uses data from a tarball that is extracted by a separate
`Uncompress_<tarball>.tar.gz` test. Without a `DEPENDS` declaration, CTest may
schedule the conversion test before the extraction test.

**Example:**
```cmake
# BAD — gtractConcatDwi_Concat_Dicom has no DEPENDS
add_test(NAME GTRACTTest_gtractConcatDwi_Concat_Dicom
  COMMAND ... --inputVolume ${DWITestFileDir}/PhilipsAchieva1, ...
)
# The multi-dicom variant already has the correct DEPENDS:
set_property(TEST GTRACTTest_gtractConcatDwi_Concat_multi_Dicom
  APPEND PROPERTY DEPENDS Uncompress_PhilipsAchieva1.tar.gz)
```

**Fix:** Add the missing DEPENDS:
```cmake
add_test(NAME GTRACTTest_gtractConcatDwi_Concat_Dicom
  COMMAND ... --inputVolume ${DWITestFileDir}/PhilipsAchieva1, ...
)
set_property(TEST GTRACTTest_gtractConcatDwi_Concat_Dicom
  APPEND PROPERTY DEPENDS Uncompress_PhilipsAchieva1.tar.gz)
```

**How to find missing dependencies:**
```bash
# Find tests that reference extracted data directories
grep -n 'inputVolume\|inputDir\|TestFileDir' <TestSuite/CMakeLists.txt>
# For each data dir, find the matching Uncompress_ test
ctest -N | grep 'Uncompress_<DataName>'
# Check if the test has DEPENDS on the Uncompress test
grep 'DEPENDS.*<DataName>' <TestSuite/CMakeLists.txt>
```

---

## Pattern 2 — Unconditional `add_dependencies` on optional target

**Symptom:** CMake configure fails with:
```
CMake Error at TestSuite/CMakeLists.txt:4 (add_dependencies):
  The dependency target "InstallReferenceAtlas" of target
  "BRAINSPosteriorToContinuousClassTestDriver" does not exist.
```

**Root cause:** A test driver unconditionally depends on an optional target
(`InstallReferenceAtlas`, `InstallTestData`, etc.) that is only created when the
corresponding module is enabled (`USE_ReferenceAtlas=ON`).

**Fix:** Guard with `if(TARGET ...)`:
```cmake
# BAD:
add_dependencies(BRAINSPosteriorToContinuousClassTestDriver InstallReferenceAtlas)

# GOOD:
if(TARGET InstallReferenceAtlas)
  add_dependencies(BRAINSPosteriorToContinuousClassTestDriver InstallReferenceAtlas)
endif()
```

This allows the module to build and its non-atlas tests to run even when
`USE_ReferenceAtlas=OFF`, while still preserving the data dependency when the
atlas is enabled.

---

## Pattern 3 — Two sets of tarballs (DWIConvert-specific)

In BRAINSTools, DWIConvert has TWO sets of tarballs:

| Tarball | Extracts to | Used by |
|---------|-------------|---------|
| `DWIConvertSiemensTrioTimTest.tar.gz` | `DWIConvertSiemensTrioTimTest/` | CMake-named test (unused) |
| `SiemensTrioTim1.tar.gz` | `SiemensTrioTim1/` | Actual conversion test input |

Running `ctest -R DWIConvert` only extracts the `DWIConvert`-prefixed tarballs.
The conversion tests need the vendor-named tarballs.

**Fix:** Run ALL `Uncompress_` tests before the conversion tests:
```bash
ctest -R 'Uncompress_' -j4 -q     # extract all data
ctest -R DWIConvert -j<N>          # now run conversion tests
```

---

## Pattern 4 — Parallel output race (two tests write same file)

**Symptom:** Tests pass serially but fail non-deterministically under `-j N`.

**Root cause:** Two tests write to the same `TEST_TEMP_OUTPUT` path.

**Audit:** Find duplicate output paths across `add_test`/`ExternalData_add_test`:
```python
import re
content = open('TestSuite/CMakeLists.txt').read()
outputs = {}
for m in re.finditer(r'TEST_TEMP_OUTPUT[=\s]+(\S+)', content):
    path = m.group(1)
    outputs.setdefault(path, []).append(m.start())
for path, locs in outputs.items():
    if len(locs) > 1:
        print(f"CONFLICT: {path} at positions {locs}")
```

**Fix:** Give each test a unique output filename:
```cmake
# BAD — both write to GeSignaHDxTest.nrrd:
-D TEST_TEMP_OUTPUT=${TstOutput}/GeSignaHDxTest.nrrd   # DWIConvertGeSignaHdxTest
-D TEST_TEMP_OUTPUT=${TstOutput}/GeSignaHDxTest.nrrd   # DWIConvertGeSignaHdxBMatrixTest

# GOOD:
-D TEST_TEMP_OUTPUT=${TstOutput}/GeSignaHDxTest.nrrd        # original
-D TEST_TEMP_OUTPUT=${TstOutput}/GeSignaHDxBMatrixTest.nrrd # BMatrix variant
```

**Commit prefix:** `BUG: Fix parallel test race: give BMatrix tests unique output filenames`
