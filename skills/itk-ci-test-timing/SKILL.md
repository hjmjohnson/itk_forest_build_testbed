---
name: itk-ci-test-timing
version: 1.0.0
purpose: Identify tests exceeding a time budget on GitHub Actions CI runners, and configure CTest to exclude them (CTEST_CUSTOM_TESTS_IGNORE + -E flag).
description: >-
  Identify tests exceeding a time budget on GitHub Actions CI runners, and
  configure CTest to exclude them (CTEST_CUSTOM_TESTS_IGNORE + -E flag).
  Use for BRAINSTools, ITK, Slicer, or any CMake/CTest project where slow tests
  consume CI runner time. Trigger on: "slow CI tests", "CI timeout", "tests take
  too long", "exclude slow tests", "BCD tests", "disable slow tests in CI".
triggers:
  - itk-ci-test-timing
  - /itk-ci-test-timing
user_invocable: true
cmd: false
argument_hint: "[--budget seconds] [--repo OWNER/REPO]"
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
    network_required: true
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

# ITK/CTest CI Test Timing — Identify and Exclude Slow Tests

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-ci-test-timing — Find and exclude slow CI tests

Usage:
  /itk-ci-test-timing                         Measure timings from latest CI run
  /itk-ci-test-timing --budget 120            Flag tests over 120s
  /itk-ci-test-timing --repo owner/repo       Target a specific repo
```

GitHub-hosted CI runners are slower than developer machines.  Tests acceptable
locally can cause multi-hour CI runs.  This skill covers measuring, deciding,
and correctly excluding slow tests.

## Step 1 — Measure actual CI timings

Download the Test.xml artifact from a recent CI run:

```bash
# List runs with test data
gh run list --repo <owner>/<repo> --workflow build.yml \
  --json databaseId,conclusion,headBranch --limit 10

# Download artifact
gh api "repos/<owner>/<repo>/actions/runs/<RUN_ID>/artifacts" \
  --jq '.artifacts[] | {name, id}'
gh api "repos/<owner>/<repo>/actions/artifacts/<ARTIFACT_ID>/zip" \
  > logs.zip && unzip -d logs logs.zip

# Parse timings from Test.xml
python3 - <<'PY'
import xml.etree.ElementTree as ET
tree = ET.parse('logs/.../Testing/<TAG>/Test.xml')
tests = []
for t in tree.getroot().iter('Test'):
    name = t.findtext('Name','')
    tm = t.find(".//NamedMeasurement[@name='Execution Time']/Value")
    status = t.get('Status','')
    if tm: tests.append((float(tm.text), name, status))
for t,n,s in sorted(tests,reverse=True)[:30]:
    print(f'{t:8.1f}s  {s:<10}  {n}')
PY
```

## Step 2 — Determine the threshold

Default threshold: **5 minutes (300 s)** on CI.  Apply a **CI/local multiplier**
based on measured data:

```
CI multiplier = CI_time / local_time
```

For BRAINSTools (Ubuntu GitHub-hosted / macOS arm64 local): **~6x**

So the local threshold to pre-screen: `300 / 6 = 50 s`.

Run locally:
```bash
ctest --timeout 360 -j<N> -E '<already-excluded>'
cat Testing/Temporary/CTestCostData.txt | sort -t' ' -k3 -rn | head -30
```

## Step 3 — Classify tests over threshold

For each test > 300 s on CI:

| Category | Action |
|----------|--------|
| Long-running algorithm test (e.g., BCD, BRAINSABC) | Exclude from CI; keep locally |
| Checker test that depends on excluded parent (e.g., `chk_BCDTest_*`) | Also exclude (it will abort/fail) |
| Pre-existing GCC/Clang baseline divergence | Exclude; file follow-up to regenerate baseline |
| Test requiring missing data (ReferenceAtlas, DICOM tarballs) | Exclude until data accessible |

## Step 4 — Exclude in two places

### 4a. `CMake/CTestCustom.cmake.in` (project-level, affects all CTest modes)

```cmake
set(CTEST_CUSTOM_TESTS_IGNORE
  ${CTEST_CUSTOM_TESTS_IGNORE}
  # BCD tests — 75+ minutes each on CI (BCDTestForLandmarkCompare = 4531 s)
  BCDTestForLandmarkCompare
  BCDTest_ForceACPoint
  # ... etc
  # Companion checker tests that abort when parent is excluded
  chk_BCDTest_ForceACPoint
  chk_a_BCDTestForLandmarkCompare
  )
```

### 4b. `.github/workflows/build.yml` (belt-and-suspenders for fresh CMake runs)

```yaml
run: |
  ctest -D ExperimentalTest --schedule-random --output-on-failure \
    -j ${{ matrix.config.parallel }} \
    -E '^(BCD|chk_.*BCD|BRAINSABCSmallTest)'
```

The `-E` regex is applied BEFORE `CTestCustom.cmake` is generated on a fresh
configure; both mechanisms are needed for reliable exclusion.

**Regex pitfall:** `^BCD` excludes tests starting with "BCD" but NOT `chk_BCDTest_*`.
Use `^(BCD|chk_.*BCD)` to cover both.

## Step 5 — Document the reason

In the commit message and `CTestCustom.cmake.in` comment, record:
1. The measured CI time
2. Why exclusion is appropriate (too slow, data missing, pre-existing failure)
3. What would be needed to re-enable (new baseline, smaller test data, etc.)

## Checker tests

Any test whose name starts with `chk_` and depends on a parent test needs to be
excluded if the parent is excluded.  Otherwise it aborts with "Subprocess aborted"
— a misleading false failure.

Pattern: if parent `XTest` is excluded, also exclude `chk_XTest`, `chk_a_XTest`,
`chk_i_XTest`.

## Re-enabling tests

To re-enable a test excluded for baseline divergence:
1. Run the test on the target platform (Linux/GCC)
2. Save output: `cp output.nii.gz <TestName>.result.nii.gz`
3. Compute hash: `sha512sum <TestName>.result.nii.gz`
4. Add `<TestName>.result.nii.gz.sha512` to the ExternalData store
5. Remove from exclusion lists
6. Verify CI passes
