# Plastimatch ITKv6 support — MR series design

Date: 2026-06-17
Status: approved (design); implementation plan pending

## Goal

Make Plastimatch build and pass its test suite against **ITKv6 (6.0)** while
**preserving ITKv5** support, delivered as a series of small, independently
reviewable upstream Merge Requests.

## Decisions (durable conventions: see memory `itkv6-downstream-port-conventions`)

- **Target / workflow:** upstream `gitlab.com/plastimatch/plastimatch`. Topic
  branches pushed to fork `git@gitlab.com:hjmjohnson/plastimatch.git` (remote
  `hjmjohnson` on `forest_git_repos/Plastimatch`) → MR against upstream
  `master`. **No MR is opened without explicit per-MR human approval** after
  local build+test (global pr-no-unsolicited rule).
- **Slicing:** one MR per incompatibility **category**.
- **Guard policy:** `ITK_VERSION_MAJOR` guard only when the v6 form is the
  *preferred* path and the v5 form is on a removal track (the guard documents
  the transition; deleting `#else` later finishes it). Otherwise write
  **version-neutral** code (compiles on v5 and v6, no `#ifdef`).
- **Scoping is empirical, not theoretical.** Anchor on what actually fails
  against ITK 6.0; deprecated-but-working items (e.g. `ITK_USE_FILE`, which the
  forest build proved still works in 6.0) are forward-looking cleanup, not
  blockers.
- **Scope boundaries:** ITK-coupled bundled code (`libs/demons_itk_insight`,
  `libs/ransac`) is in scope; frozen vendored ITK snapshots (`libs/itk-4.13.2-*`)
  are never touched; non-ITK portability fixes ship as **separate,
  clearly-labeled** MRs.
- **YAGNI:** skip cosmetic-only modernizations that still compile (`SetInput`
  piping, `GetPointer`, `ITK_LIBRARIES`→`ITK::` targets).

## MR series

### Tier 1 — ITKv6 support (labeled "ITKv6")

| MR | Category | Files | Approach | Priority |
|----|----------|-------|----------|----------|
| **V6-1** | vcl/vnl legacy tokens | `libs/demons_itk_insight/*.hxx/.txx`, `LOGDomainDemons/*` | Neutral: `vcl_*`→`std::`, `vnl_math_*`→`vnl_math::`, then delete the `vcl_legacy_aliases.h` include | Empirical blocker |
| **V6-2** | itk macro hygiene (trailing `;`) | `libs/ransac/SphereParametersEstimator.h` + audit all `itk*Macro` in `src/`, `libs/ransac`, `libs/demons_itk_insight` | Neutral: add `;` | Empirical blocker (surfaces only when the ransac template is compiled — see V6-test) |
| ~~V6-3~~ | ~~CMake `ITK_USE_FILE`~~ | — | **DROPPED 2026-06-17** | `ITK_USE_FILE`/`UseITK.cmake` is only *deprecated* in 6.0.0, not removed; it still supplies Plastimatch's global include dirs + IO factory registration. Guarding it out breaks the v6 build. Not a 6.0 blocker; revisit if a future ITK removes it. |
| **V6-4** | `itkConfigure.h` includes | `src/base/{itk_warp.cxx,plm_itk.h,itkClampCastImageFilter.h}` | Audit → remove if unneeded, else guard | Cleanup |
| **V6-5** | `itkStaticConstMacro`→`static constexpr` | `libs/demons_itk_insight/**` (~10 sites) | Neutral | Removal-track cleanup |
| **V6-6** | version-guard housekeeping | `src/base/xform.cxx`, `src/util/itk_scale.cxx`, `src/register/registration.cxx` | drop obsolete `==3`; add `>=6` where logic diverges | Housekeeping |

**V6-test** (folds into V6-2 or its own MR): register the bundled
`libs/ransac/Testing/SphereParametersEstimatorTest.cxx` in ctest (upstream
never `add_subdirectory`s it) so the `vnl_levenberg_marquardt` path is actually
compiled and executed. This is what surfaces the V6-2 macro `;` bug.

### Tier 2 — Separate portability MRs (NOT labeled ITKv6)

| MR | Issue | Files / approach |
|----|-------|------------------|
| **P-A** | `FindSSE.cmake` crashes on arm64 (empty `machdep.cpu.features` → `STRING(REGEX REPLACE)` arg error) | `cmake/FindSSE.cmake`: guard empty CPUINFO |
| **P-B** | C++17 removed `throw()` exception spec | `src/sys/plm_exception.h:15` |
| **P-D** | `find_package(ITK)` aborts: modern ITK exports (`proxTV`) reference `OpenMP::OpenMP_CXX`, which Plastimatch's bundled `FindOpenMP.cmake` never creates | `cmake/FindOpenMP.cmake`: create the `OpenMP::OpenMP_CXX` imported target (version-neutral). Discovered in Task 1. |
| **P-C** | **Bump vendored dlib 19.1 → latest 19.24.x** | Drop modern dlib source into `libs/dlib-19.24.x/`, update `src/CMakeLists.txt:102` `DLIB_INCLUDE_DIR`, remove `libs/dlib-19.1/`, fix any dlib API drift in `src/segment` (autolabel: svm/krr/krls/mlp trainers, `cmd_line_parser`) and `src/sys` (`dlib_threads`). Modern dlib is C++14/17-clean, so this subsumes both the `char_traits<unsigned int>` and `std::binary_function` breakages. Alternative considered: targeted patch of dlib-19.1 (rejected — user chose the bump). |

### Dropped (YAGNI)

`SetInput`/`GetPointer`/`ITK_LIBRARIES`→`ITK::` — compile fine, cosmetic only.

## Sequencing

Each MR's content is independent, but a green v6 build (macOS/arm64 + conda
libc++) requires the empirical blockers together: **V6-1, V6-2 + P-A, P-B, P-C**.
Maintain an **integration branch** with all fixes; validate there; peel each
MR's isolated diff for submission.

Order: **P-A → P-C → P-B → V6-1 → V6-2** (= full build + ctest green on v6,
milestone) → **V6-3 → V6-6** (cleanup, re-validate after each).

## Validation (evidence attached to every MR)

Dual-ITK build via the forest `USE_SYSTEM_ITK`:
- **v6** = forest default (`main` / `eigen-nonlinear-lm`, 6.0) — already wired.
- **v5** = a second forest (`FOREST_REFERENCE_SUFFIX`) with ITK at the latest
  `v5.4.x` tag.

Each MR must show, against **both** v5 and v6: green Plastimatch build +
`ctest` (579 tests incl. `ransac-sphere-estimator`). **Verify by artifact, not
pipe exit code.**

## Per-MR submission checklist (gates `glab mr create`)

1. isolated diff on a topic branch off upstream `master`
2. built + tested against v5 **and** v6 locally
3. MR body: 1–3 line summary + collapsed `<details>` (PR-message-format rule);
   `Co-Authored-By` only for humans
4. explicit human go-ahead → open as draft/WIP

## Testbed implications

Once V6-1/V6-2/P-A/P-C land (or are staged), the corresponding testbed patches
in `bin/setup-itk-downstream-testbed.sh` become redundant and should be retired
(`_patch_plastimatch_dlib_unicode`, `_patch_plastimatch_vcl_aliases`, the SSE2
flag, the `itkNewMacro` semicolon edit in `_patch_plastimatch_ransac_test`).
Keep the ransac-test ctest registration until upstream accepts V6-test.
