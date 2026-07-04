# CMakePresets Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move declarative per-consumer CMake configuration out of the ~280-line `configure_one()` shell into reviewable, IDE-runnable CMakePresets fragments, backed by a generated `CMakeUserPresets.json` overlay, and migrate build/install trees to a nested layout that lets ccache share cache entries across forest locations.

**Architecture:** Committed hidden preset fragments in `kit/cmake/presets/*.json` (base + per-ITK-version + per-consumer) are `include`d by a thin, gitignored `CMakeUserPresets.json` overlay that the wrapper writes per consumer with forest-discovered dirs. The wrapper keeps discovery, source patching, and orchestration, and gains an overlay-generator. Build trees move to `${FOREST}/${PKG}/build` (nested in source) and installs to `${FOREST}/installed/${PKG}` so `CCACHE_BASEDIR=${sourceDir}` covers the whole build.

**Tech Stack:** Bash (the wrapper), CMake ≥3.28 presets schema v6, ccache, pixi, Ninja.

## Global Constraints

- Repo of record for ALL work in this plan: the **kit** repo `hjmjohnson/itk_forest_build_testbed`. Never commit into a consumer worktree.
- Verify by artifact, not pipe exit code: a build is "passing" only when its binary/library exists on disk.
- Committed preset fragments live in `cmake/presets/` (slash — NOT `cmake-presets/`, which the global `cmake-*` ignore swallows) and are NOT named `CMakePresets.json` (globally ignored).
- Generated overlay is literally `CMakeUserPresets.json` (globally auto-ignored; do not add to any tracked ignore).
- Preset schema `version: 6`.
- New layout: source `${FOREST}/${PKG}`, build `${FOREST}/${PKG}/build`, install `${FOREST}/installed/${PKG}`.
- ccache base is the per-package source dir via preset `environment.CCACHE_BASEDIR = ${sourceDir}`.
- Cross-platform (macOS BSD + Linux GNU): `grep -E` not `-P`; no `sed -i` in-place traps.
- The wrapper path is `bin/setup-itk-downstream-testbed.sh`; run tasks from the kit root `~/src/itk_forest_build_testbed`.
- All builds run inside the pixi env (`pixi run bash bin/setup-itk-downstream-testbed.sh …`).

---

## File Structure

**Created (committed, kit repo):**
- `cmake/presets/00-base.json` — hidden `itk-forest-base`: generator, build type, ccache launchers+basedir, compilers, rpath, `binaryDir`/`installDir`, ignore-prefix.
- `cmake/presets/10-itk-v6.json` — hidden `itk-forest-itk-v6` (inherits base): FFTW, ~45 `Module_*`, build flags, zlib_hint.
- `cmake/presets/10-itk-v5.json` — hidden `itk-forest-itk-v5` (inherits base): minimal default-module set.
- `cmake/presets/consumer-ANTs.json` — hidden configure `itk-forest-ants` + build/test/workflow presets.
- `cmake/presets/consumer-<X>.json` — one per remaining consumer (Task 8 recipe).

**Created (generated at runtime, gitignored, per consumer source dir):**
- `${FOREST}/${PKG}/CMakeUserPresets.json` — `include`s the consumer fragment, adds discovered dirs.

**Modified (kit repo):**
- `bin/setup-itk-downstream-testbed.sh` — layout helpers, overlay generator, `configure_one()` delegating to `cmake --preset`, `build_one()`/`install_itk()` path updates, dir-finder updates.
- `bin/run-matrix.sh` — loop over `cmake --workflow --preset` + artifact assert.

---

## Task 1: Route all forest-level build/install paths through helpers (behavior-preserving)

Introduce `build_dir()` / `install_dir()` returning the CURRENT paths, and replace every forest-level `-build`/`-install` literal with a call. No path changes yet — this isolates the risky rename from the layout flip.

**Files:**
- Modify: `bin/setup-itk-downstream-testbed.sh` (lines ~160-161, 233-258, 322, 668, 695, 985, 1043, 1056)

**Interfaces:**
- Produces: `build_dir <name>` → echoes the forest build tree for `<name>`; `install_dir <name>` → echoes the forest install tree. Task 2 changes only these two bodies.

- [ ] **Step 1: Add the two helpers** near the other path helpers (after line 161).

```bash
# Forest-level build/install tree locations. Task-2 flips these two bodies to
# the nested layout; every caller goes through them so the change is one place.
build_dir(){   echo "${FOREST}/${1}-build"; }
install_dir(){ echo "${FOREST}/installed/${1}"; }   # install already uses installed/ target
```

Note: `install_dir` is authored at its FINAL value now (only ITK installs today; `ITK_INSTALL` is the sole caller, so changing it here is safe and testable immediately). `build_dir` starts at the OLD value.

- [ ] **Step 2: Replace forest-level build literals with `$(build_dir NAME)`.**

Replace these (forest-level trees the wrapper itself creates or discovers):
- L160 `ITK_BUILD="${FOREST}/ITK-build"` → `ITK_BUILD="$(build_dir ITK)"`
- L233-234 `"${FOREST}/VTK-build"` → `"$(build_dir VTK)"` (leave `BRAINSTools-build/VTK-Release-build` — inner SuperBuild tree — unchanged)
- L240,242 `${FOREST}/OpenIGTLink-build` → `$(build_dir OpenIGTLink)`
- L244,246 `${FOREST}/OpenIGTLinkIO-build` → `$(build_dir OpenIGTLinkIO)`
- L250,252 `${FOREST}/vtkAddon-build` → `$(build_dir vtkAddon)`
- L256,258 `${FOREST}/IGSIO-build` → `$(build_dir IGSIO)`
- L322 `${FOREST}/ANTs-build/ANTS-build` → `$(build_dir ANTs)/ANTS-build`
- L668 `b="${FOREST}/VTK-build"` → `b="$(build_dir VTK)"`
- L695 `b="${FOREST}/${name}-build"` → `b="$(build_dir "$name")"`
- L985 `b="${FOREST}/${1}-build"` → `b="$(build_dir "$1")"`

**Leave unchanged** (inner SuperBuild EP trees owned by the consumer, not the wrapper): L197,200 `Slicer-build/VTK-build`, L619 `BRAINSTools-build/...EP*-build`, L895 `Slicer-build/Slicer-build`, L916 `ITKDCMTK_ExtProject-build`, and the `grep -vE '/[A-Za-z]+-build/'` patch filters (L589,601,611,634).

- [ ] **Step 3: Update `ITK_INSTALL` and the status filter.**

- L161 `ITK_INSTALL="${FOREST}/ITK-install"` → `ITK_INSTALL="$(install_dir ITK)"`
- L1056 `grep -vE -- '-build$'` still hides old-style siblings; leave as-is for now (Task 2 revisits).

- [ ] **Step 4: Syntax-check and dry verify no path drift.**

Run: `bash -n bin/setup-itk-downstream-testbed.sh && echo SYNTAX_OK`
Expected: `SYNTAX_OK`

Run: `pixi run bash bin/setup-itk-downstream-testbed.sh status 2>&1 | head` (or the list command) to confirm the script still parses variables.
Expected: no "unbound variable"/path errors.

- [ ] **Step 5: Confirm ITK build tree is still found at the OLD location.**

Run: `test -f "$(pixi run bash -c 'source /dev/stdin <<<"$(sed -n "1,170p" bin/setup-itk-downstream-testbed.sh)"; echo')" ` — simpler: just verify the existing built ITK still resolves:
Run: `ls build_forest-svdc/ITK-build/ITKConfig.cmake`
Expected: file exists (helper returns old path, so discovery is unchanged).

- [ ] **Step 6: Commit.**

```bash
git add bin/setup-itk-downstream-testbed.sh
git commit -m "ENH: route forest build/install paths through build_dir/install_dir helpers"
```

---

## Task 2: Flip to nested build layout + source-relative ccache base

Change `build_dir` to the nested layout and set `CCACHE_BASEDIR`. This is the one behavioral change; verify with a real rebuild-to-artifact.

**Files:**
- Modify: `bin/setup-itk-downstream-testbed.sh` (`build_dir` body; `common_cmake_args` env; L1056 status filter)

**Interfaces:**
- Consumes: `build_dir`/`install_dir` from Task 1.
- Produces: nested build trees at `${FOREST}/${PKG}/build`.

- [ ] **Step 1: Flip the helper body.**

```bash
build_dir(){   echo "${FOREST}/${1}/build"; }
```

- [ ] **Step 2: Add source-relative ccache base to `common_cmake_args`.**

In `common_cmake_args` (L301-312), replace the forest-relative file-prefix-map with source-relative, and export `CCACHE_BASEDIR`. Since `common_cmake_args` emits `-D` flags (not env), set the map to the source dir via CMake and rely on the preset env for `CCACHE_BASEDIR` once presets land; for the pre-preset interim, export it in `build_one`. Concretely, change L304-305:

```bash
    "-DCMAKE_C_FLAGS_INIT=-ffile-prefix-map=${s:-${FOREST}}=." \
    "-DCMAKE_CXX_FLAGS_INIT=-ffile-prefix-map=${s:-${FOREST}}=." \
```

and in `build_one` (before the `cmake --build`, ~L985), add:

```bash
  export CCACHE_BASEDIR="${FOREST}/${name}"
```

(`common_cmake_args` is called with `$s` = source dir in scope for consumers; for ITK the two-pass path also has `$s`. `${s:-${FOREST}}` keeps a safe fallback.)

- [ ] **Step 3: Update the status filter for nested builds.**

L1056: old `grep -vE -- '-build$'` no longer hides builds (they're now `${PKG}/build` subdirs, not siblings). Change to list only source dirs:
```bash
  ls -1 "${FOREST}" 2>/dev/null | grep -vE -- '-build$' || true
```
(unchanged is fine — nested `build/` is inside `${PKG}`, so top-level `ls` already only shows `${PKG}`; no sibling `-build` dirs remain to filter. Leave as-is.)

- [ ] **Step 4: Clean-rebuild ITK to the new location, verify artifact.**

Run:
```bash
rm -rf build_forest-svdc/ITK-build   # old sibling; new tree will be build_forest-svdc/ITK/build
pixi run bash bin/setup-itk-downstream-testbed.sh build ITK 2>&1 | tail -5
```
Expected: build completes.

Run (artifact check, not exit code):
```bash
ls build_forest-svdc/ITK/build/ITKConfig.cmake && \
ls build_forest-svdc/ITK/build/lib/libITKCommon-*.dylib 2>/dev/null || \
ls build_forest-svdc/ITK/build/lib/libITKCommon-*.so 2>/dev/null
```
Expected: `ITKConfig.cmake` and a libITKCommon exist under the NEW nested path.

- [ ] **Step 5: Rebuild ANTs against the relocated ITK, verify artifact.**

Run:
```bash
rm -rf build_forest-svdc/ANTs-build
pixi run bash bin/setup-itk-downstream-testbed.sh build ANTs 2>&1 | tail -5
ls build_forest-svdc/ANTs/build/ANTS-build/Examples/sccan
```
Expected: `sccan` binary exists under the new nested path.

- [ ] **Step 6: Commit.**

```bash
git add bin/setup-itk-downstream-testbed.sh
git commit -m "ENH: nest build trees in source (\${PKG}/build) + source-relative CCACHE_BASEDIR"
```

---

## Task 3: Create the base preset fragment + schema smoke test

**Files:**
- Create: `cmake/presets/00-base.json`
- Create: `cmake/presets/.smoke/CMakeLists.txt` (throwaway configure target for validation)

**Interfaces:**
- Produces: hidden preset `itk-forest-base` with generator, ccache, rpath, compilers, `binaryDir`, `installDir`, ccache basedir env.

- [ ] **Step 1: Write `00-base.json`.**

```json
{
  "$schema": "https://cmake.org/cmake/help/latest/_downloads/3e2d73bff478d88a7de0de736ba5e361/schema.json",
  "version": 6,
  "configurePresets": [
    {
      "name": "itk-forest-base",
      "hidden": true,
      "generator": "Ninja",
      "binaryDir": "${sourceDir}/build",
      "installDir": "${sourceParentDir}/installed/${sourceDirName}",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Release",
        "BUILD_TESTING": "ON",
        "CMAKE_C_COMPILER": "$env{CC}",
        "CMAKE_CXX_COMPILER": "$env{CXX}",
        "CMAKE_C_COMPILER_LAUNCHER": "ccache",
        "CMAKE_CXX_COMPILER_LAUNCHER": "ccache",
        "CMAKE_IGNORE_PREFIX_PATH": "/opt/homebrew",
        "CMAKE_BUILD_RPATH": "$env{CONDA_PREFIX}/lib",
        "CMAKE_C_FLAGS_INIT": "-ffile-prefix-map=${sourceDir}=.",
        "CMAKE_CXX_FLAGS_INIT": "-ffile-prefix-map=${sourceDir}=."
      },
      "environment": {
        "CCACHE_BASEDIR": "${sourceDir}"
      }
    }
  ]
}
```

- [ ] **Step 2: Create the smoke fixture.**

`cmake/presets/.smoke/CMakeLists.txt`:
```cmake
cmake_minimum_required(VERSION 3.28)
project(PresetSmoke NONE)
message(STATUS "SMOKE binaryDir=${CMAKE_BINARY_DIR}")
```

`cmake/presets/.smoke/CMakeUserPresets.json`:
```json
{
  "version": 6,
  "include": ["../00-base.json"],
  "configurePresets": [
    { "name": "smoke", "inherits": "itk-forest-base" }
  ]
}
```

- [ ] **Step 3: Validate the base preset resolves.**

Run:
```bash
cd cmake/presets/.smoke && pixi run --manifest-path ../../../pixi.toml cmake --preset smoke -N 2>&1 | grep -E 'CMAKE_BUILD_TYPE|Preset'; cd -
```
Expected: preset `smoke` loads without "invalid preset"/"unknown macro"; `-N` (dry) lists the cache var. If ccache/CC env vars are unset outside a build, run under `pixi run` so `$env{CC}` resolves.

- [ ] **Step 4: Commit.**

```bash
git add cmake/presets/00-base.json cmake/presets/.smoke/CMakeLists.txt cmake/presets/.smoke/CMakeUserPresets.json
git commit -m "ENH: add itk-forest-base preset fragment + schema smoke fixture"
```

---

## Task 4: Add the overlay generator to the wrapper

**Files:**
- Modify: `bin/setup-itk-downstream-testbed.sh` (new function near `common_cmake_args`)

**Interfaces:**
- Consumes: `build_dir`; kit root path.
- Produces: `write_overlay <name> <inherits-preset> [cachevar=val ...]` — writes `${FOREST}/${name}/CMakeUserPresets.json` including the consumer fragment and a `forest-<name>-local` configure preset carrying the passed cache vars.

- [ ] **Step 1: Add `KIT_PRESETS` path constant** near `SCRIPT_DIR` (top of file):

```bash
KIT_PRESETS="${SCRIPT_DIR%/bin}/cmake/presets"   # SCRIPT_DIR is .../kit/bin
```

- [ ] **Step 2: Add the generator function.**

```bash
# write_overlay NAME INHERITS FRAGMENT [KEY=VAL ...]
#   NAME      consumer name (source dir is ${FOREST}/NAME)
#   INHERITS  hidden configure preset to inherit (e.g. itk-forest-ants)
#   FRAGMENT  basename of the committed fragment under cmake/presets (e.g. consumer-ANTs.json)
#   KEY=VAL   discovered cacheVariables (ITK_DIR=..., VTK_DIR=...)
write_overlay(){
  local name="$1" inherits="$2" fragment="$3"; shift 3
  local src="${FOREST}/${name}" cvs="" kv
  for kv in "$@"; do
    [ -n "$kv" ] || continue
    cvs="${cvs}$(printf '        "%s": "%s",\n' "${kv%%=*}" "${kv#*=}")"
  done
  cvs="${cvs%,$'\n'}"   # strip trailing comma+newline
  cat > "${src}/CMakeUserPresets.json" <<EOF
{
  "version": 6,
  "include": ["${KIT_PRESETS}/${fragment}"],
  "configurePresets": [
    {
      "name": "forest-${name}-local",
      "inherits": "${inherits}",
      "cacheVariables": {
${cvs}
      }
    }
  ]
}
EOF
}
```

- [ ] **Step 3: Unit-test the generator in isolation.**

Run:
```bash
pixi run bash -c '
  set -e; source <(sed -n "1,60p" bin/setup-itk-downstream-testbed.sh) 2>/dev/null || true
  FOREST=/tmp/ovtest KIT_PRESETS=/tmp/kp SCRIPT_DIR="$PWD/bin"
  mkdir -p /tmp/ovtest/Demo
  # inline the function under test:
  '"$(sed -n '/^write_overlay(){/,/^}/p' bin/setup-itk-downstream-testbed.sh)"'
  write_overlay Demo itk-forest-ants consumer-ANTs.json ITK_DIR=/x/ITK/build VTK_DIR=/y/VTK/build
  cat /tmp/ovtest/Demo/CMakeUserPresets.json
'
```
Expected: valid JSON with `forest-Demo-local`, `include` pointing at `consumer-ANTs.json`, and both cache vars (no trailing comma).

- [ ] **Step 4: Validate JSON parses.**

Run: `python3 -m json.tool /tmp/ovtest/Demo/CMakeUserPresets.json >/dev/null && echo JSON_OK`
Expected: `JSON_OK`

- [ ] **Step 5: Commit.**

```bash
git add bin/setup-itk-downstream-testbed.sh
git commit -m "ENH: add write_overlay generator for per-consumer CMakeUserPresets.json"
```

---

## Task 5: Author the ITK v6 and v5 preset fragments

**Files:**
- Create: `cmake/presets/10-itk-v6.json`, `cmake/presets/10-itk-v5.json`

**Interfaces:**
- Produces: hidden presets `itk-forest-itk-v6`, `itk-forest-itk-v5` (both `inherits: itk-forest-base`).

- [ ] **Step 1: Write `10-itk-v6.json`** with the FFTW flags, the full module list (verbatim from `configure_one` L766-794, 810-812), build flags, and the zlib hint. Cache values are strings.

```json
{
  "version": 6,
  "include": ["00-base.json"],
  "configurePresets": [
    {
      "name": "itk-forest-itk-v6",
      "hidden": true,
      "inherits": "itk-forest-base",
      "cacheVariables": {
        "ITK_USE_FFTWD": "ON", "ITK_USE_FFTWF": "ON", "ITK_USE_SYSTEM_FFTW": "ON",
        "FFTW_INCLUDE_PATH": "$env{CONDA_PREFIX}/include",
        "FFTW_LIB_SEARCHPATH": "$env{CONDA_PREFIX}/lib",
        "ITK_USE_SYSTEM_ZLIB": "ON",
        "ZLIB_ROOT": "$env{CONDA_PREFIX}",
        "BUILD_EXAMPLES": "ON", "ITK_USE_BRAINWEB_DATA": "ON",
        "ITK_BUILD_DEFAULT_MODULES": "ON", "ITK_BUILD_ALL_MODULES": "ON",
        "Module_AdaptiveDenoising": "ON", "Module_AnisotropicDiffusionLBR": "ON",
        "Module_BoneEnhancement": "ON", "Module_BoneMorphometry": "ON",
        "Module_BSplineGradient": "ON", "Module_Cuberille": "ON",
        "Module_FastBilateral": "ON", "Module_FixedPointInverseDisplacementField": "ON",
        "Module_Fpfh": "ON", "Module_GenericLabelInterpolator": "ON",
        "Module_GrowCut": "ON", "Module_HigherOrderAccurateGradient": "ON",
        "Module_IOFDF": "ON", "Module_IOMeshMZ3": "ON", "Module_IOMeshSTL": "ON",
        "Module_IOMeshSWC": "ON", "Module_IOTransformDCMTK": "ON", "Module_ITKDCMTK": "ON",
        "Module_ITKIODCMTK": "ON",
        "Module_IsotropicWavelets": "ON", "Module_LabelErodeDilate": "ON",
        "Module_MGHIO": "ON", "Module_MeshNoise": "ON", "Module_MeshToPolyData": "ON",
        "Module_MinimalPathExtraction": "ON", "Module_Montage": "ON",
        "Module_MorphologicalContourInterpolation": "ON",
        "Module_MultipleImageIterator": "ON", "Module_ParabolicMorphology": "ON",
        "Module_PhaseSymmetry": "ON", "Module_PolarTransform": "ON",
        "Module_PrincipalComponentsAnalysis": "ON", "Module_RANSAC": "ON",
        "Module_RLEImage": "ON", "Module_SimpleITKFilters": "ON",
        "Module_SmoothingRecursiveYvvGaussianFilter": "ON",
        "Module_SplitComponents": "ON", "Module_Strain": "ON",
        "Module_StructuralSimilarity": "ON", "Module_SubdivisionQuadEdgeMeshFilter": "ON",
        "Module_TextureFeatures": "ON", "Module_Thickness3D": "ON",
        "Module_TotalVariation": "ON", "Module_TwoProjectionRegistration": "ON",
        "Module_VariationalRegistration": "ON",
        "Module_ITKReview": "ON",
        "Module_TractographyTRX": "OFF"
      }
    }
  ]
}
```

`$comment` note for the zlib line (schema v10+ supports `$comment`; on v6 keep the rationale in the spec, not the JSON): the `ITK_USE_SYSTEM_ZLIB=ON` is the temporary 2026-07-02 setting under review — see spec Future section.

- [ ] **Step 2: Write `10-itk-v5.json`** (minimal path — L754-756):

```json
{
  "version": 6,
  "include": ["00-base.json"],
  "configurePresets": [
    {
      "name": "itk-forest-itk-v5",
      "hidden": true,
      "inherits": "itk-forest-base",
      "cacheVariables": {
        "BUILD_TESTING": "OFF", "BUILD_EXAMPLES": "OFF",
        "ITK_BUILD_DEFAULT_MODULES": "ON",
        "ITK_USE_FFTWD": "ON", "ITK_USE_FFTWF": "ON", "ITK_USE_SYSTEM_FFTW": "ON",
        "FFTW_INCLUDE_PATH": "$env{CONDA_PREFIX}/include",
        "FFTW_LIB_SEARCHPATH": "$env{CONDA_PREFIX}/lib"
      }
    }
  ]
}
```

- [ ] **Step 3: Validate both parse.**

Run: `for f in cmake/presets/10-itk-v6.json cmake/presets/10-itk-v5.json; do python3 -m json.tool "$f" >/dev/null && echo "OK $f"; done`
Expected: `OK` for both.

- [ ] **Step 4: Commit.**

```bash
git add cmake/presets/10-itk-v6.json cmake/presets/10-itk-v5.json
git commit -m "ENH: add ITK v6/v5 preset fragments (module list, FFTW, zlib hint)"
```

---

## Task 6: Wire ITK's configure to the preset + verify CMakeCache parity

**Files:**
- Modify: `bin/setup-itk-downstream-testbed.sh` (`configure_one` ITK branch: the full-v6 path L807-819 and the v5 path L754-756)

**Interfaces:**
- Consumes: `write_overlay`, `itk-forest-itk-v6`/`v5`, `build_dir`.
- Produces: ITK configured via `cmake --preset forest-ITK-local`.

- [ ] **Step 1: Replace the v6 `_itk_cmake` invocation with overlay + preset.**

In the v6 branch, after computing `_itk_vtk`, replace the `_itk_cmake=(cmake -S … )` array and its two-pass calls (L809-819) with:

```bash
    local itk_over=(ITK_DIR="")   # ITK builds itself; no ITK_DIR needed
    local vtk_kv=()
    [ -n "${_itk_vtk}" ] && vtk_kv=(VTK_DIR="${_itk_vtk}" Module_ITKVtkGlue=ON \
                                    BUILD_TESTING=OFF BUILD_EXAMPLES=OFF ITK_USE_BRAINWEB_DATA=OFF)
    write_overlay ITK itk-forest-itk-v6 10-itk-v6.json "${vtk_kv[@]}"
    _overlay_vnl_headers
    # First pass fetches remote modules (may fail on examples/-less remote); stub, retry.
    ( cd "${FOREST}/ITK" && pixi_cmake --preset forest-ITK-local ) || true
    _stub_remote_examples
    ( cd "${FOREST}/ITK" && pixi_cmake --preset forest-ITK-local )
    return
```

Where `pixi_cmake` is `cmake` (the wrapper already runs inside pixi). If a helper is wanted, add `pixi_cmake(){ cmake "$@"; }`. The `-S/-B` are implied by preset `sourceDir`/`binaryDir`; run from the source dir so `${sourceDir}` resolves to `${FOREST}/ITK`.

- [ ] **Step 2: Replace the v5 minimal invocation.**

L754-756 becomes:
```bash
      local v5_kv=()
      [ "${ITK_WITH_DCMTK:-0}" = 1 ] && v5_kv=(Module_ITKDCMTK=ON Module_ITKIODCMTK=ON)
      write_overlay ITK itk-forest-itk-v5 10-itk-v5.json "${v5_kv[@]}"
      ( cd "${FOREST}/ITK" && cmake --preset forest-ITK-local )
      return
```

- [ ] **Step 3: Capture the OLD ITK cache as a baseline.**

Run (before rebuilding): `cp build_forest-svdc/ITK/build/CMakeCache.txt /tmp/itk-cache-before.txt 2>/dev/null; wc -l /tmp/itk-cache-before.txt`
Expected: a line count (this is the Task-2 relocated build's cache).

- [ ] **Step 4: Reconfigure ITK via the preset, verify artifact.**

Run:
```bash
rm -rf build_forest-svdc/ITK/build
pixi run bash bin/setup-itk-downstream-testbed.sh build ITK 2>&1 | tail -8
ls build_forest-svdc/ITK/build/ITKConfig.cmake
```
Expected: `ITKConfig.cmake` exists; and `build_forest-svdc/ITK/CMakeUserPresets.json` was generated.

- [ ] **Step 5: Diff the material cache vars against baseline.**

Run:
```bash
for v in ITK_USE_FFTWD Module_ITKReview Module_ITKVtkGlue ITK_BUILD_ALL_MODULES ITK_USE_SYSTEM_ZLIB; do
  grep -E "^${v}:" build_forest-svdc/ITK/build/CMakeCache.txt
done
```
Expected: each matches the intended fragment value (`FFTWD=ON`, `ITKReview=ON`, etc.). If any differs from `/tmp/itk-cache-before.txt`, reconcile the fragment.

- [ ] **Step 6: Commit.**

```bash
git add bin/setup-itk-downstream-testbed.sh
git commit -m "ENH: configure ITK via CMakePresets overlay (v6/v5), retire configure_one ITK soup"
```

---

## Task 7: Proving consumer — ANTs fragment + wiring + workflow validation

**Files:**
- Create: `cmake/presets/consumer-ANTs.json`
- Modify: `bin/setup-itk-downstream-testbed.sh` (`configure_one` ANTs case L824-845)

**Interfaces:**
- Consumes: `write_overlay`, `itk_dir`.
- Produces: `cmake --workflow --preset forest-ANTs` (configure→build→test) for ANTs.

- [ ] **Step 1: Write `consumer-ANTs.json`** (default, non-MAX flags; MAX variants stay overlay-injected).

```json
{
  "version": 6,
  "include": ["00-base.json"],
  "configurePresets": [
    {
      "name": "itk-forest-ants",
      "hidden": true,
      "inherits": "itk-forest-base",
      "cacheVariables": {
        "USE_SYSTEM_ITK": "ON",
        "USE_VTK": "OFF",
        "USE_TractographyTRX": "OFF"
      }
    }
  ],
  "buildPresets": [
    { "name": "forest-ANTs", "configurePreset": "forest-ANTs-local", "jobs": 8 }
  ],
  "testPresets": [
    { "name": "forest-ANTs", "configurePreset": "forest-ANTs-local",
      "output": { "outputOnFailure": true } }
  ],
  "workflowPresets": [
    { "name": "forest-ANTs", "steps": [
      { "type": "configure", "name": "forest-ANTs-local" },
      { "type": "build",     "name": "forest-ANTs" },
      { "type": "test",      "name": "forest-ANTs" }
    ] }
  ]
}
```

Note: `forest-ANTs-local` is defined only in the generated overlay; the committed build/test/workflow presets reference it by name and resolve at load time across `CMakePresets`+`CMakeUserPresets`.

- [ ] **Step 2: Wire the ANTs case to the overlay.**

Replace L844-845 (`cmake -S "$s" -B "$b" … "${ants_mods[@]}"`) with:

```bash
                 local ants_kv=(ITK_DIR="$(itk_dir)")
                 # MAX-module toggles become overlay cache vars (variant, not default)
                 if [ "${ANTS_MAX_MODULES:-0}" = 1 ]; then
                   ants_kv+=(USE_VTK=ON BUILD_ALL_ANTS_APPS=ON)
                   [ -n "${ANTS_VTK_DIR:-}" ] && ants_kv+=(USE_SYSTEM_VTK=ON VTK_DIR="${ANTS_VTK_DIR}")
                 fi
                 write_overlay ANTs itk-forest-ants consumer-ANTs.json "${ants_kv[@]}"
                 ( cd "$s" && cmake --preset forest-ANTs-local ) ;;
```

- [ ] **Step 3: Reconfigure + build ANTs via preset, verify artifact.**

Run:
```bash
rm -rf build_forest-svdc/ANTs/build
pixi run bash bin/setup-itk-downstream-testbed.sh build ANTs 2>&1 | tail -6
ls build_forest-svdc/ANTs/build/ANTS-build/Examples/sccan
```
Expected: `sccan` exists; `build_forest-svdc/ANTs/CMakeUserPresets.json` was generated with `ITK_DIR`.

- [ ] **Step 4: Drive the full workflow preset (configure→build→test) directly.**

Run:
```bash
cd build_forest-svdc/ANTs && pixi run --manifest-path ../../pixi.toml cmake --workflow --preset forest-ANTs 2>&1 | tail -15; cd -
```
Expected: configure and build steps succeed. (Tests may be long; a `-R sccan_HELP_LONG` subset can be validated separately. If FFTW rpath still bites here, that's the deferred `ITK_USE_FFTWD=OFF` item — out of scope for this task.)

- [ ] **Step 5: Commit.**

```bash
git add cmake/presets/consumer-ANTs.json bin/setup-itk-downstream-testbed.sh
git commit -m "ENH: configure ANTs via CMakePresets + workflow preset (proving consumer)"
```

---

## Task 8: Roll out remaining consumers + reduce run-matrix

Repeat the Task-7 pattern per consumer, then simplify the matrix driver. This task is mechanical; each consumer is one commit.

**Files:**
- Create: `cmake/presets/consumer-<X>.json` for each of: BRAINSTools, Slicer, SlicerExtensions, elastix, MITK, c3d, Plastimatch, SimpleITK, OpenIGTLink, OpenIGTLinkIO, vtkAddon, IGSIO, PlusLib, BioCell.
- Modify: `bin/setup-itk-downstream-testbed.sh` (each `configure_one` case), `bin/run-matrix.sh`.

**Interfaces:**
- Consumes: `write_overlay`, per-consumer dir finders.

- [ ] **Step 1: For each consumer, extract its static `-D` flags into `consumer-<X>.json`.**

Recipe (per consumer, using its `configure_one` case as the source of truth):
1. Static flags (constant `-D…=ON/OFF`) → `cacheVariables` of a hidden `itk-forest-<x>` preset inheriting `itk-forest-base`.
2. Discovered dirs (`$(itk_dir)`, `$(vtk_dir)`, `$(igsio_dir)`, …) and env-gated MAX toggles → passed to `write_overlay` as `KEY=VAL`.
3. Add build/test/workflow presets mirroring `consumer-ANTs.json` (rename `ANTs`→`<X>`).
4. Replace the case's `cmake -S "$s" -B "$b" …` with `write_overlay <X> itk-forest-<x> consumer-<X>.json <discovered kv…>` + `( cd "$s" && cmake --preset forest-<X>-local )`.
5. Keep every `_patch_*` call in the case BEFORE the `write_overlay`/`cmake --preset` line — patches have no preset hook.

Validate each: `python3 -m json.tool cmake/presets/consumer-<X>.json && rm -rf build_forest-svdc/<X>/build && pixi run bash bin/setup-itk-downstream-testbed.sh build <X> 2>&1 | tail -4` then artifact-check the consumer's primary binary/library on disk. Commit per consumer: `ENH: configure <X> via CMakePresets`.

- [ ] **Step 2: Reduce `run-matrix.sh` to workflow + artifact assert.**

Replace the per-consumer configure/build invocation with:
```bash
for c in "${MATRIX_CONSUMERS[@]}"; do
  patch_if_needed "$c"                       # existing _patch_* dispatch, if any
  ( cd "${FOREST}/${c}" && cmake --workflow --preset "forest-${c}" ) || true
  assert_artifact "$c"                        # existing on-disk binary/library check — the SCORER
done
```
Keep `assert_artifact` exactly as-is: workflow exit code is not artifact proof (Global Constraints).

- [ ] **Step 3: Run the full matrix, confirm scoreboard matches pre-restructure.**

Run: `pixi run bash bin/run-matrix.sh 2>&1 | tee /tmp/matrix-after.log | tail -30`
Expected: the artifact scoreboard shows the same PASS set as the last known-good pre-restructure run (compare against a saved `itk-forest-ctest-summary.txt`).

- [ ] **Step 4: Commit the matrix change** (consumer fragments were committed per-consumer in Step 1).

```bash
git add bin/run-matrix.sh
git commit -m "ENH: drive run-matrix via cmake --workflow presets, keep artifact scorer"
```

---

## Self-Review

**Spec coverage:**
- Layer 1 committed fragments → Tasks 3,5,7,8. ✓
- Layer 2 generated overlay + `include` + gitignored name → Task 4 (generator), used in 6,7,8. ✓
- Layer 3 shell keeps discovery/patch/orchestration → preserved; patches stay before `cmake --preset` (Task 7 Step 2 note, Task 8 Step 1.5). ✓
- Directory layout (nested build, installed/) + ccache basedir rationale → Tasks 1,2 + base preset env (Task 3). ✓
- `$env{}`/`$penv{}` usage → base + itk fragments use `$env{}`. ✓
- workflowPresets + "workflow ≠ artifact proof" → Tasks 7,8, scorer retained. ✓
- Patched-consumer limitation → Task 7/8 keep patches in shell. ✓
- Future/deferred FFTW-off, zlib → not implemented here; zlib carried as the current `ON` value (Task 5), noted. ✓
- Global-ignore compatibility (names, `cmake/presets/` slash) → Global Constraints + Task 3. ✓

**Placeholder scan:** No TBD/TODO; every code step shows real content. `consumer-<X>.json` in Task 8 is a mechanical recipe (repeat-the-pattern is permitted for N identical consumers, with the concrete ANTs template in Task 7). ✓

**Type/name consistency:** `build_dir`/`install_dir` (T1→T2), `write_overlay NAME INHERITS FRAGMENT KV…` (T4→T6,T7,T8), preset names `itk-forest-base`/`itk-forest-itk-v6`/`itk-forest-itk-v5`/`itk-forest-ants`, overlay preset `forest-<name>-local`, workflow `forest-<name>` — consistent across tasks. ✓
