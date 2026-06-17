# Plastimatch ITKv6 Support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Plastimatch build + pass `ctest` against ITKv6 (6.0) while preserving ITKv5, delivered as a categorized series of upstream GitLab MRs.

**Architecture:** Validate via the itk_forest_build_testbed `USE_SYSTEM_ITK` forest against BOTH a v5.4.x ITK and a v6 ITK. Build a single integration branch carrying every fix (to get a green dual-ITK build), then peel each category into an isolated topic branch off upstream `master` for one MR. No MR is opened without explicit per-MR human approval.

**Tech Stack:** CMake/Ninja, pixi conda toolchain (clang/libc++), ccache, ITK 5.4 + 6.0, dlib, git, `glab` (GitLab CLI).

## Global Constraints

- Upstream: `gitlab.com/plastimatch/plastimatch`; fork remote `hjmjohnson` = `git@gitlab.com:hjmjohnson/plastimatch.git`; MRs target upstream `master`.
- **No MR opened without explicit per-MR human approval** after local build+test (pr-no-unsolicited).
- Guard policy: `ITK_VERSION_MAJOR` guard ONLY when v6 is preferred AND v5 path is removal-track; else version-neutral (no `#ifdef`).
- Scope: ITK-coupled bundled code (`libs/demons_itk_insight`, `libs/ransac`) in scope; frozen `libs/itk-4.13.2-*` NEVER touched; non-ITK portability fixes are SEPARATE, non-"ITKv6"-labeled MRs.
- Verify by artifact (binary/lib on disk + ctest count), never by pipe exit code.
- Each MR: isolated diff, built+tested against v5 AND v6, body per PR-message-format (1–3 line summary + `<details>`), `Co-Authored-By` humans only.
- Forest paths: v6 forest = `build_forest/` (ITK `build_forest/ITK-build`); v5 forest = `build_forest-itkv5/` (set via `FOREST_REFERENCE_SUFFIX=itkv5`). Repo root: `/Users/johnsonhj/src/itk_forest_build_testbed`.
- All `pixi run` / `ctest` commands run from the repo root unless noted.

---

### Task 0: Stand up the dual-ITK validation harness

**Files:**
- Modify (local clone config only, not committed): `forest_git_repos/ITK` remotes
- No source files changed.

**Interfaces:**
- Produces: a built v5.4.x ITK at `build_forest-itkv5/ITK-build/ITKConfig.cmake` and a built v6 ITK at `build_forest/ITK-build/ITKConfig.cmake`; both usable as `ITK_DIR` by later tasks.

- [ ] **Step 1: Confirm the v6 ITK is built**

Run: `ls /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/ITK-build/ITKConfig.cmake`
Expected: path prints (already built from prior work).

- [ ] **Step 2: Pick the latest v5.4 tag**

Run: `git -C /Users/johnsonhj/src/itk_forest_build_testbed/forest_git_repos/ITK tag -l 'v5.4*' | sort -V | tail -3`
Expected: prints tags (e.g. `v5.4.0 v5.4.1 v5.4.2 v5.4.3`). Use the highest as `<V5TAG>`.

- [ ] **Step 3: Materialize the v5 reference forest source trees**

Run: `cd /Users/johnsonhj/src/itk_forest_build_testbed && FOREST_REFERENCE_SUFFIX=itkv5 pixi run bash bin/setup-itk-downstream-testbed.sh checkout ITK Plastimatch`
Expected: creates `build_forest-itkv5/ITK` and `build_forest-itkv5/Plastimatch` worktrees.

- [ ] **Step 4: Point the v5 forest ITK at the tag and build it**

Run: `cd /Users/johnsonhj/src/itk_forest_build_testbed && FOREST_REFERENCE_SUFFIX=itkv5 ITK_REF=<V5TAG> pixi run repoint-itk && FOREST_REFERENCE_SUFFIX=itkv5 pixi run build-ITK`
Expected: ends with `ITKConfig.cmake` present; verify next.

**NOTE (2026-06-17):** v5.4.6's `Module_Montage` fails to compile with this
toolchain (`ImageScanlineIterator` CTAD error), which halts the build and
leaves `proxTV` and ~4 other module libs unbuilt → Plastimatch can't link on
v5. Reconfigure the v5 ITK build with `-DModule_Montage=OFF` (Plastimatch uses
neither Montage nor proxTV directly) and rebuild so ALL remaining module libs
(incl. `libitkproxTV-5.4.a`) are produced. Verify by counting `.a` libs against
the v6 build.

- [ ] **Step 5: Verify both ITKs by artifact**

Run: `ls build_forest/ITK-build/ITKConfig.cmake build_forest-itkv5/ITK-build/ITKConfig.cmake && grep -h Version_VERSION build_forest*/ITK-build/ITKConfig.cmake 2>/dev/null | head`
Expected: both configs exist; versions show 6.x and 5.4.x.

- [ ] **Step 6: No commit (harness is local clone state only)**

Note: forest builds are git-ignored; nothing to commit.

---

### Task 1: Integration branch — green Plastimatch build on BOTH ITKs

This branch carries every fix at once to prove the end state and to give later tasks a known-good reference for peeling isolated diffs. It is NOT an MR.

**Files:**
- Create branch: `itkv6-integration` in `forest_git_repos/Plastimatch` (checked out at `build_forest/Plastimatch`)
- Modify: all files listed in Tasks 2–10 (applied together here)

**Interfaces:**
- Consumes: Task 0 ITKs.
- Produces: `build_forest/Plastimatch-build/plastimatch` (v6) and `build_forest-itkv5/Plastimatch-build/plastimatch` (v5), both with `ctest` green.

- [ ] **Step 1: Create the integration branch off upstream master**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed/forest_git_repos/Plastimatch
git fetch origin
git -C /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch checkout -B itkv6-integration origin/master
```
Expected: switched to `itkv6-integration` at origin/master tip.

- [ ] **Step 2: Apply every fix from Tasks 2–10**

Apply, in order, the edits specified in Task 2 (P-A), Task 3 (P-C), Task 4 (P-B), Task 5 (V6-1), Task 6 (V6-2 + V6-test), Task 7 (V6-3), Task 8 (V6-4), Task 9 (V6-5), Task 10 (V6-6) — to the `build_forest/Plastimatch` worktree.

- [ ] **Step 3: Build + ctest on v6**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed
rm -rf build_forest/Plastimatch-build
pixi run build-Plastimatch 2>&1 | tail -3
test -x build_forest/Plastimatch-build/plastimatch && echo ARTIFACT_OK
pixi run --manifest-path pixi.toml ctest --test-dir build_forest/Plastimatch-build -j8 2>&1 | grep "tests passed"
```
Expected: `ARTIFACT_OK`; `100% tests passed ... out of 580` (579 + any unblocked by the dlib bump).

- [ ] **Step 4: Build + ctest on v5**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed
# sync the v5 worktree to the same integration tree:
git -C build_forest-itkv5/Plastimatch fetch origin && git -C build_forest-itkv5/Plastimatch checkout -B itkv6-integration-v5 build_forest/Plastimatch
rm -rf build_forest-itkv5/Plastimatch-build
FOREST_REFERENCE_SUFFIX=itkv5 pixi run build-Plastimatch 2>&1 | tail -3
test -x build_forest-itkv5/Plastimatch-build/plastimatch && echo ARTIFACT_OK
pixi run --manifest-path pixi.toml ctest --test-dir build_forest-itkv5/Plastimatch-build -j8 2>&1 | grep "tests passed"
```
Expected: `ARTIFACT_OK`; `100% tests passed`.

- [ ] **Step 5: Commit the integration branch (local reference only)**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch
git add -A
git commit -m "WIP: ITKv6 + portability integration (reference; do not push)"
```
Expected: commit recorded. This branch is never pushed; it is the peel source.

---

### Task 2: P-A — FindSSE.cmake arm64 guard (separate MR)

**Files:**
- Modify: `cmake/FindSSE.cmake` (Darwin branch, ~line 35: `EXEC_PROGRAM(... machdep.cpu.features ...)` then `STRING(REGEX REPLACE ... ${CPUINFO})`)

**Interfaces:**
- Produces: configure succeeds on arm64 with `SSE2_FOUND` false.

- [ ] **Step 1: Reproduce the failure (test)**

Run: `cd /Users/johnsonhj/src/itk_forest_build_testbed && rm -rf build_forest/Plastimatch-build && pixi run build-Plastimatch 2>&1 | grep -i "FindSSE.cmake"` (with PLM_CONFIG_ENABLE_SSE2 forced ON)
Expected: `STRING sub-command REGEX, mode REPLACE needs at least 5 arguments` — confirms the empty-CPUINFO crash.

- [ ] **Step 2: Guard empty CPUINFO in the Darwin branch**

Edit `cmake/FindSSE.cmake` Darwin branch to short-circuit when the sysctl yields nothing:
```cmake
ELSEIF (CMAKE_SYSTEM_NAME MATCHES "Darwin")
  EXEC_PROGRAM ("/usr/sbin/sysctl -n machdep.cpu.features"
    OUTPUT_VARIABLE CPUINFO)
  # Apple Silicon: machdep.cpu.features is empty; no SSE on arm64.
  IF (NOT CPUINFO)
    SET (SSE2_FOUND   false CACHE BOOL "SSE2 Available?")
    SET (SSE3_FOUND   false CACHE BOOL "SSE3 Available?")
    SET (SSSE3_FOUND  false CACHE BOOL "SSSE3 Available?")
    SET (SSE4_1_FOUND false CACHE BOOL "SSE4.1 Available?")
  ELSE ()
    # ... existing STRING(REGEX ...) detection unchanged ...
  ENDIF ()
```
(Wrap the existing Darwin `STRING(REGEX...)` block in the `ELSE()`.)

- [ ] **Step 3: Verify configure no longer crashes**

Run: `cd /Users/johnsonhj/src/itk_forest_build_testbed && rm -rf build_forest/Plastimatch-build && PLM_ENABLE_SSE2=ON pixi run build-Plastimatch 2>&1 | grep -iE "FindSSE|CPU does not support SSE2|Configuring done"`
Expected: `CPU does not support SSE2.` and no REGEX error; configure completes.

- [ ] **Step 4: Open the MR (GATED — needs explicit human go-ahead)**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch
git checkout -B fix/findsse-arm64 origin/master
git checkout itkv6-integration -- cmake/FindSSE.cmake
git commit -am "COMP: Guard FindSSE.cmake against empty CPU features on Apple Silicon"
# WAIT for human approval, then:
git push hjmjohnson fix/findsse-arm64
glab mr create --repo plastimatch/plastimatch --source-branch fix/findsse-arm64 --target-branch master --draft --title "COMP: FindSSE arm64 guard" --description-file /tmp/mr-pa.md
```
Expected: do NOT run push/glab until the human approves this specific MR.

---

### Task 3: P-C — Bump vendored dlib 19.1 → 19.24.x (separate MR)

**Files:**
- Create: `libs/dlib-19.24.6/` (modern dlib source tree)
- Delete: `libs/dlib-19.1/`
- Modify: `src/CMakeLists.txt:102` (`DLIB_INCLUDE_DIR`)
- Possibly modify: `src/segment/*` (svm/krr/krls/mlp trainers, `cmd_line_parser`), `src/sys/dlib_threads.cxx` for API drift

**Interfaces:**
- Produces: Plastimatch compiles its dlib usage under C++17 libc++ with no `char_traits<uint32>` / `binary_function` errors.

- [ ] **Step 1: Fetch the target dlib release**

```bash
cd /tmp && curl -fsSLO http://dlib.net/files/dlib-19.24.tar.bz2 && tar xjf dlib-19.24.tar.bz2
grep -h "VERSION" dlib-19.24/dlib/revision.h
```
Expected: prints `19 / 24 / N`. Use exact patch as `<DLIBVER>`.

- [ ] **Step 2: Drop the new source into the worktree, remove old**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch
rm -rf libs/dlib-19.1
cp -R /tmp/dlib-19.24 libs/dlib-19.24
```

- [ ] **Step 3: Update the hardcoded include dir**

Edit `src/CMakeLists.txt:102`:
```cmake
  set (DLIB_INCLUDE_DIR "${PLM_SOURCE_DIR}/libs/dlib-19.24")
```

- [ ] **Step 4: Build on v6; fix any dlib API drift surfaced**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed
rm -rf build_forest/Plastimatch-build
pixi run build-Plastimatch 2>&1 | grep -iE "error:|dlib" | head -20
```
Expected: no `char_traits<unsigned int>` / `binary_function` errors. If trainer/`cmd_line_parser` API drift errors appear, fix the call sites in `src/segment/` per the dlib 19.24 API (show the specific diff when encountered). Re-run until clean.

- [ ] **Step 5: Verify by artifact + ctest (v6)**

```bash
test -x /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch-build/plastimatch && echo ARTIFACT_OK
pixi run --manifest-path /Users/johnsonhj/src/itk_forest_build_testbed/pixi.toml ctest --test-dir /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch-build -R "autolabel|mabs|train" -j8 2>&1 | grep "tests passed"
```
Expected: `ARTIFACT_OK`; dlib-dependent (autolabel/svm) tests pass.

- [ ] **Step 6: Retire the now-redundant testbed dlib patch**

Edit `/Users/johnsonhj/src/itk_forest_build_testbed/bin/setup-itk-downstream-testbed.sh`: remove `_patch_plastimatch_dlib_unicode` and its invocation, and drop `-D_LIBCPP_ENABLE_CXX17_REMOVED_UNARY_BINARY_FUNCTION` from the Plastimatch `CMAKE_CXX_FLAGS` (modern dlib no longer needs it). Commit separately to the testbed.

- [ ] **Step 7: Open the MR (GATED — needs explicit human go-ahead)**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch
git checkout -B deps/bump-dlib-19.24 origin/master
git checkout itkv6-integration -- libs/dlib-19.24 src/CMakeLists.txt
git rm -r libs/dlib-19.1
git commit -m "COMP: Bump vendored dlib 19.1 -> <DLIBVER> for C++17/libc++ support"
# WAIT for approval, then push hjmjohnson + glab mr create --draft
```

---

### Task 4: P-B — Remove throw() spec (separate MR)

**Files:**
- Modify: `src/sys/plm_exception.h:15`

- [ ] **Step 1: Locate the spec**

Run: `grep -n "throw()" /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch/src/sys/plm_exception.h`
Expected: line 15 `virtual ~Plm_exception () throw() {}`.

- [ ] **Step 2: Replace `throw()` with `noexcept`**

Edit line 15:
```cpp
  virtual ~Plm_exception () noexcept {}
```

- [ ] **Step 3: Verify build (v6)**

Run: `cd /Users/johnsonhj/src/itk_forest_build_testbed && pixi run build-Plastimatch 2>&1 | grep -iE "plm_exception|error:" | head`
Expected: no errors referencing plm_exception.

- [ ] **Step 4: Open the MR (GATED)**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch
git checkout -B cpp17/noexcept-dtor origin/master
git checkout itkv6-integration -- src/sys/plm_exception.h
git commit -am "STYLE: Use noexcept instead of removed C++17 throw() spec"
# WAIT for approval, then push + glab mr create --draft
```

---

### Task 5: V6-1 — vcl/vnl legacy tokens in bundled demons (ITKv6 MR)

**Files:**
- Modify: `libs/demons_itk_insight/*.hxx`, `*.txx`, `LOGDomainDemons/*` containing `vcl_*` or `vnl_math_*` tokens or the `vcl_legacy_aliases.h` include.

**Interfaces:**
- Produces: demons code compiles on v6 with no removed-VXL-symbol errors and no shim header.

- [ ] **Step 1: Inventory the tokens (test)**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch
grep -rlE "vcl_(abs|ceil|fabs|log|pow|sqrt)|vnl_math_(abs|sqr|min|max)|vcl_legacy_aliases" libs/demons_itk_insight
```
Expected: list of files (the demons .hxx/.txx and LOGDomainDemons).

- [ ] **Step 2: Replace tokens with version-neutral forms**

For each file from Step 1, apply:
```bash
perl -i -pe 's/\bvcl_(abs|ceil|fabs|log|pow|sqrt)\b/std::$1/g;
             s/\bvnl_math_(abs|sqr|min|max)\b/vnl_math::$1/g;
             s{^\s*#\s*include\s*"vcl_legacy_aliases\.h".*\n}{}g;' <file>
```
Then ensure each touched TU includes `<cmath>` and `vnl/vnl_math.h` (add after the first existing include if absent).

- [ ] **Step 3: Delete the testbed shim dependency for these files**

The bundled code must compile WITHOUT `vcl_legacy_aliases.h`. Confirm no file still references it:
```bash
grep -rl "vcl_legacy_aliases" libs/demons_itk_insight || echo NONE_LEFT
```
Expected: `NONE_LEFT`.

- [ ] **Step 4: Build on v6 (without the testbed force-include shim)**

Temporarily build with the shim disabled to prove the source is self-sufficient:
```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed
rm -rf build_forest/Plastimatch-build
PLM_NO_VCL_SHIM=1 pixi run build-Plastimatch 2>&1 | grep -iE "error:|vcl_|vnl_math_" | head
```
(Implement `PLM_NO_VCL_SHIM` to skip `_patch_plastimatch_vcl_aliases` and drop the `-include` flag, OR just verify by removing the shim file first.)
Expected: no vcl/vnl errors.

- [ ] **Step 5: Build on v5**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed
git -C build_forest-itkv5/Plastimatch checkout -B v6-1-v5 build_forest/Plastimatch
rm -rf build_forest-itkv5/Plastimatch-build
FOREST_REFERENCE_SUFFIX=itkv5 pixi run build-Plastimatch 2>&1 | grep -iE "error:" | head
test -x build_forest-itkv5/Plastimatch-build/plastimatch && echo V5_OK
```
Expected: `V5_OK`, no errors (vnl_math:: and std:: exist in v5).

- [ ] **Step 6: Open the MR (GATED)**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch
git checkout -B itkv6/demons-vcl-vnl-modernize origin/master
git checkout itkv6-integration -- libs/demons_itk_insight
git commit -am "COMP: ITKv6 - replace removed vcl_/vnl_math_ tokens in bundled demons"
# WAIT for approval, then push + glab mr create --draft
```

---

### Task 6: V6-2 — itk macro trailing semicolons + register ransac test (ITKv6 MR)

**Files:**
- Modify: `libs/ransac/SphereParametersEstimator.h` (+ any other `itk*Macro` without trailing `;`)
- Modify: `Testing/CMakeLists.txt` (register the ransac sphere test)

**Interfaces:**
- Produces: `ransac-sphere-estimator` ctest target that compiles `SphereParametersEstimator.h` and runs the `vnl_levenberg_marquardt` path.

- [ ] **Step 1: Find macros missing a trailing semicolon (test)**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch
grep -rnE "itk(New|Type|GetObject|SetObject|GetConst)Macro\s*\([^)]*\)\s*$" src libs/ransac libs/demons_itk_insight | grep -v ";"
```
Expected: includes `libs/ransac/SphereParametersEstimator.h:32: itkNewMacro( Self )`.

- [ ] **Step 2: Add the missing semicolons**

```bash
perl -i -pe 's/^(\s*itk(?:New|Type|GetObject|SetObject|GetConst)Macro\s*\([^)]*\))\s*$/$1;/' <each file from Step 1>
```

- [ ] **Step 3: Register the ransac sphere test in the main build**

Append to `Testing/CMakeLists.txt`:
```cmake
# RANSAC sphere-estimator unit test (exercises vnl_levenberg_marquardt)
add_executable (ransac_sphere_estimator_test
  ${PLM_SOURCE_DIR}/libs/ransac/Testing/SphereParametersEstimatorTest.cxx)
target_include_directories (ransac_sphere_estimator_test PRIVATE
  ${PLM_SOURCE_DIR}/libs/ransac ${PLM_SOURCE_DIR}/libs/ransac/Common)
target_link_libraries (ransac_sphere_estimator_test ${ITK_LIBRARIES})
add_test (NAME ransac-sphere-estimator COMMAND ransac_sphere_estimator_test)
```

- [ ] **Step 4: Build + run the new test on v6**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed
rm -rf build_forest/Plastimatch-build && pixi run build-Plastimatch 2>&1 | tail -2
pixi run --manifest-path pixi.toml ctest --test-dir build_forest/Plastimatch-build -R ransac-sphere-estimator -V 2>&1 | grep -iE "Geometric least squares|Passed"
```
Expected: geometric LM estimate prints; `ransac-sphere-estimator ... Passed`.

- [ ] **Step 5: Build + run on v5**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed
git -C build_forest-itkv5/Plastimatch checkout -B v6-2-v5 build_forest/Plastimatch
rm -rf build_forest-itkv5/Plastimatch-build && FOREST_REFERENCE_SUFFIX=itkv5 pixi run build-Plastimatch 2>&1 | tail -2
pixi run --manifest-path pixi.toml ctest --test-dir build_forest-itkv5/Plastimatch-build -R ransac-sphere-estimator 2>&1 | grep "tests passed"
```
Expected: `100% tests passed`.

- [ ] **Step 6: Open the MR (GATED)**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch
git checkout -B itkv6/itk-macro-semicolons origin/master
git checkout itkv6-integration -- libs/ransac/SphereParametersEstimator.h Testing/CMakeLists.txt
git commit -am "COMP: ITKv6 - add trailing ; to itk*Macro; build+register ransac sphere test"
# WAIT for approval, then push + glab mr create --draft
```

---

### Task 7: V6-3 — DROPPED

**Status: DROPPED (2026-06-17).** Premise was wrong: `ITK_USE_FILE` /
`UseITK.cmake` is only *deprecated* in ITK 6.0.0, not removed — it still
supplies Plastimatch's global ITK include dirs and IO factory registration.
Guarding it out broke the v6 build (`itkApproximateSignedDistanceMapImageFilter.h`
not found). Per the empirical-not-theoretical principle it is not a 6.0 port
blocker; revisit only if/when a future ITK removes `UseITK.cmake`. Original
text retained below for history.

<details><summary>Original (do not implement)</summary>

**Files:**
- Modify: `cmake/HandleITK.cmake:16`, `libs/ransac/CMakeLists.txt:11`, `extra/api_examples/CMakeLists.txt:16`

- [ ] **Step 1: Locate the includes (test)**

Run: `cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch && grep -rn "ITK_USE_FILE" cmake libs/ransac/CMakeLists.txt extra`
Expected: 3 hits.

- [ ] **Step 2: Guard each with a version check**

Replace each `include (${ITK_USE_FILE})` with:
```cmake
if (ITK_VERSION_MAJOR LESS 6)
  include (${ITK_USE_FILE})
endif ()
```
(ITKv6 supplies usage requirements via imported targets; `ITK_USE_FILE` is removal-track.)

- [ ] **Step 3: Verify configure on both ITKs**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed
rm -rf build_forest/Plastimatch-build && pixi run build-Plastimatch 2>&1 | grep -iE "Configuring done|error" | head
git -C build_forest-itkv5/Plastimatch checkout -B v6-3-v5 build_forest/Plastimatch
rm -rf build_forest-itkv5/Plastimatch-build && FOREST_REFERENCE_SUFFIX=itkv5 pixi run build-Plastimatch 2>&1 | grep -iE "Configuring done|error" | head
```
Expected: both configure + build clean.

- [ ] **Step 4: Open the MR (GATED)**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch
git checkout -B itkv6/cmake-itk-use-file origin/master
git checkout itkv6-integration -- cmake/HandleITK.cmake libs/ransac/CMakeLists.txt extra/api_examples/CMakeLists.txt
git commit -am "COMP: ITKv6 - guard removed ITK_USE_FILE behind ITK_VERSION_MAJOR<6"
# WAIT for approval, then push + glab mr create --draft
```

</details>

---

### Task 7b: P-D — FindOpenMP.cmake OpenMP::OpenMP_CXX target (separate portability MR)

**Added 2026-06-17** (discovered in Task 1). Modern ITK imported targets
(notably `proxTV`) reference `OpenMP::OpenMP_CXX` in their
`INTERFACE_LINK_LIBRARIES`; Plastimatch's bundled `FindOpenMP.cmake` only sets
`OPENMP_FLAGS`/`OPENMP_LIBRARIES` and never creates that target, so
`find_package(ITK)` aborts. Version-neutral fix.

**Files:** `cmake/FindOpenMP.cmake`

- [ ] **Step 1:** after detection, when `OPENMP_FOUND` and target absent, create it:
```cmake
if (OPENMP_FOUND AND NOT TARGET OpenMP::OpenMP_CXX)
  add_library (OpenMP::OpenMP_CXX INTERFACE IMPORTED)
  set_target_properties (OpenMP::OpenMP_CXX PROPERTIES
    INTERFACE_COMPILE_OPTIONS "${OpenMP_CXX_FLAGS}"
    INTERFACE_LINK_LIBRARIES  "${OpenMP_CXX_FLAGS}")
endif ()
```
- [ ] **Step 2:** verify `find_package(ITK)` configure succeeds on v5 (where proxTV exports the raw OpenMP ref) and v6 (harmless).
- [ ] **Step 3 (GATED):** branch `deps/findopenmp-imported-target` off origin/master, peel `cmake/FindOpenMP.cmake` from `itkv6-integration`, commit `COMP: Provide OpenMP::OpenMP_CXX imported target for modern ITK exports`; push+MR only on explicit approval.

---

### Task 8: V6-4 — Audit itkConfigure.h includes (ITKv6 MR)

**Files:**
- Modify: `src/base/itk_warp.cxx:6`, `src/base/plm_itk.h:13`, `src/base/itkClampCastImageFilter.h:7`

- [ ] **Step 1: Determine why each includes itkConfigure.h**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch
for f in src/base/itk_warp.cxx src/base/plm_itk.h src/base/itkClampCastImageFilter.h; do echo "== $f =="; grep -nE "ITK_VERSION|ITKV|ITK_USE|itkConfigure" $f; done
```
Expected: shows whether the include is used for version/feature macros.

- [ ] **Step 2: Replace with the minimal real dependency**

If only ITK version macros are needed, replace `#include "itkConfigure.h"` with `#include "itkVersion.h"` (or `itkMacro.h`); if nothing from it is used, remove the include. Apply the determined change per file.

- [ ] **Step 3: Build on v6 and v5**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed
rm -rf build_forest/Plastimatch-build && pixi run build-Plastimatch 2>&1 | grep -iE "itkConfigure|error:" | head
git -C build_forest-itkv5/Plastimatch checkout -B v6-4-v5 build_forest/Plastimatch
rm -rf build_forest-itkv5/Plastimatch-build && FOREST_REFERENCE_SUFFIX=itkv5 pixi run build-Plastimatch 2>&1 | grep -iE "itkConfigure|error:" | head
```
Expected: no itkConfigure errors on either.

- [ ] **Step 4: Open the MR (GATED)**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch
git checkout -B itkv6/itkconfigure-audit origin/master
git checkout itkv6-integration -- src/base/itk_warp.cxx src/base/plm_itk.h src/base/itkClampCastImageFilter.h
git commit -am "COMP: ITKv6 - drop/replace itkConfigure.h includes"
# WAIT for approval, then push + glab mr create --draft
```

---

### Task 9: V6-5 — itkStaticConstMacro → static constexpr in demons (ITKv6 MR)

**Files:**
- Modify: `libs/demons_itk_insight/**` files using `itkStaticConstMacro` (~10 sites)

- [ ] **Step 1: Inventory (test)**

Run: `cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch && grep -rn "itkStaticConstMacro" libs/demons_itk_insight`
Expected: ~10 sites with form `itkStaticConstMacro(Name, Type, Value);`.

- [ ] **Step 2: Replace with C++17 static constexpr**

For each `itkStaticConstMacro(Name, Type, Value);`:
```bash
perl -i -pe 's/itkStaticConstMacro\(\s*([A-Za-z_]\w*)\s*,\s*([^,]+?)\s*,\s*(.+?)\s*\)\s*;/static constexpr $2 $1 = $3;/g' <file>
```
Also replace any companion `itkGetStaticConstMacro(Name)` usages with `Name` if present.

- [ ] **Step 3: Build on v6 and v5**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed
rm -rf build_forest/Plastimatch-build && pixi run build-Plastimatch 2>&1 | grep -iE "error:|StaticConst" | head
git -C build_forest-itkv5/Plastimatch checkout -B v6-5-v5 build_forest/Plastimatch
rm -rf build_forest-itkv5/Plastimatch-build && FOREST_REFERENCE_SUFFIX=itkv5 pixi run build-Plastimatch 2>&1 | grep -iE "error:" | head
test -x build_forest/Plastimatch-build/plastimatch && test -x build_forest-itkv5/Plastimatch-build/plastimatch && echo BOTH_OK
```
Expected: `BOTH_OK`.

- [ ] **Step 4: Open the MR (GATED)**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch
git checkout -B itkv6/static-constexpr origin/master
git checkout itkv6-integration -- libs/demons_itk_insight
git commit -am "STYLE: ITKv6 - itkStaticConstMacro -> static constexpr in bundled demons"
# WAIT for approval, then push + glab mr create --draft
```

---

### Task 10: V6-6 — Version-guard housekeeping (ITKv6 MR)

**Files:**
- Modify: `src/base/xform.cxx`, `src/util/itk_scale.cxx`, `src/register/registration.cxx` (and any other file with `ITK_VERSION_MAJOR == 3` or `<= 4` branches)

- [ ] **Step 1: Inventory obsolete guards (test)**

Run: `cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch && grep -rnE "ITK_VERSION_MAJOR\s*(==\s*3|<=\s*3|<\s*4)" src`
Expected: the obsolete v3 branches.

- [ ] **Step 2: Remove dead v3 branches; add >=6 only where logic diverges**

For each hit, delete the `== 3` branch (keep the `else`/modern branch). Where a v6-specific path is genuinely needed (only if Step 3 reveals a v6 build/behavior difference), add an `#if ITK_VERSION_MAJOR >= 6` branch with the preferred form. Do not add guards speculatively.

- [ ] **Step 3: Build + full ctest on v6 and v5**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed
rm -rf build_forest/Plastimatch-build && pixi run build-Plastimatch >/dev/null 2>&1
pixi run --manifest-path pixi.toml ctest --test-dir build_forest/Plastimatch-build -j8 2>&1 | grep "tests passed"
git -C build_forest-itkv5/Plastimatch checkout -B v6-6-v5 build_forest/Plastimatch
rm -rf build_forest-itkv5/Plastimatch-build && FOREST_REFERENCE_SUFFIX=itkv5 pixi run build-Plastimatch >/dev/null 2>&1
pixi run --manifest-path pixi.toml ctest --test-dir build_forest-itkv5/Plastimatch-build -j8 2>&1 | grep "tests passed"
```
Expected: `100% tests passed` on both.

- [ ] **Step 4: Open the MR (GATED)**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed/build_forest/Plastimatch
git checkout -B itkv6/version-guard-cleanup origin/master
git checkout itkv6-integration -- src/base/xform.cxx src/util/itk_scale.cxx src/register/registration.cxx
git commit -am "STYLE: ITKv6 - drop obsolete ITKv3 version guards"
# WAIT for approval, then push + glab mr create --draft
```

---

### Task 11: Retire redundant testbed patches

After the upstream MRs that supersede them are staged/accepted, remove the now-redundant testbed patches so the forest exercises the real upstream source.

**Files:**
- Modify: `bin/setup-itk-downstream-testbed.sh`

- [ ] **Step 1: Remove superseded patch functions + invocations**

Remove `_patch_plastimatch_dlib_unicode`, `_patch_plastimatch_vcl_aliases` (and the `-include vcl_legacy_aliases.h` + `-D_LIBCPP_ENABLE_CXX17_REMOVED_UNARY_BINARY_FUNCTION` flags), the `PLM_ENABLE_SSE2` default-OFF (once P-A lands), and the `itkNewMacro` semicolon edit in `_patch_plastimatch_ransac_test` (keep the ctest registration only until V6-2 is accepted upstream).

- [ ] **Step 2: Clean rebuild proves source is self-sufficient**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed
git -C build_forest/Plastimatch checkout itkv6-integration
rm -rf build_forest/Plastimatch-build && pixi run build-Plastimatch 2>&1 | tail -2
test -x build_forest/Plastimatch-build/plastimatch && echo OK
```
Expected: `OK` with no patches applied.

- [ ] **Step 3: Commit the testbed cleanup**

```bash
cd /Users/johnsonhj/src/itk_forest_build_testbed
git add bin/setup-itk-downstream-testbed.sh
git commit -m "ENH: Retire Plastimatch patches superseded by upstream ITKv6 MRs"
```

---

## Self-Review

- **Spec coverage:** V6-1..V6-6, P-A/P-B/P-C, V6-test, dual-ITK validation, sequencing, gating, testbed cleanup — all mapped to Tasks 0–11. ✓
- **Placeholders:** `<V5TAG>` and `<DLIBVER>` are resolved by their preceding discovery steps (Task 0 Step 2, Task 3 Step 1); API-drift fixes in Task 3 Step 4 are conditional with explicit instruction to show the diff when encountered. No bare TODO/TBD. ✓
- **Type/name consistency:** test target `ransac-sphere-estimator` and exe `ransac_sphere_estimator_test` match the already-committed testbed registration; forest paths and `FOREST_REFERENCE_SUFFIX=itkv5` consistent across tasks. ✓
- **Gating:** every MR task ends with a GATED push/`glab` step that must not run before explicit human approval. ✓
