---
name: itk-dual-version-compat
version: 1.0.0
purpose: Make an ITK consumer build cleanly against both ITK release-5.4 and ITK main configured with ITK_FUTURE_LEGACY_REMOVE=ON, with no deprecation warnings on main.
description: >-
  Use when a downstream ITK project (ANTs, BRAINSTools, Slicer modules, remote
  modules, elastix, ...) must keep building against ITK 5.4 while also
  building against ITK main (ITK 6) with ITK_FUTURE_LEGACY_REMOVE=ON. Builds
  the consumer against both, scans for deprecated vnl/algo headers and other
  removals, and rewrites call sites behind one compat header per project
  using itk::bridge replacements on ITK 6. Trigger on: "build with ITK 5.4
  and ITK main", "ITK_FUTURE_LEGACY_REMOVE", "vnl_svd is deprecated",
  "migrate to itk::bridge", "dual version ITK", "itk-dual-version-compat".
triggers:
  - itk-dual-version-compat
  - /itk-dual-version-compat
  - ITK_FUTURE_LEGACY_REMOVE
  - build against ITK 5.4 and ITK main
  - migrate to itk::bridge
user_invocable: true
cmd: false
argument_hint: "<consumer source dir> [--itk-src <ITK main checkout>]"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
    - repo-edits
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "<consumer source tree>"
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: true
    network_required: false
    git_required: true
    user_confirmation_required: true
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
  skills:
    - itk-forest-refresh
  external_tools:
    - cmake
    - ninja
    - git
    - python3
  python_packages: []
  scripts:
    - scan.py
deployment:
  tier: always
  target_projects: []
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK dual-version compatibility (release-5.4 and main with FUTURE_LEGACY_REMOVE)

## Quick reference

```
itk-dual-version-compat <consumer-dir> [--itk-src ~/src/ITK]

1. Build the consumer against both ITKs (5.4; main + FUTURE_LEGACY_REMOVE)
2. scan.py lists deprecated headers, symbols, and MSVC-only macros
3. Fix through one compat header per project; call sites stay unconditional
4. Done when both builds have 0 errors and main's log has 0 "is deprecated"
```

## The target

One source tree, two ITKs, no warnings:

| ITK | Configure | What it proves |
|---|---|---|
| `release-5.4` | defaults | existing users keep building |
| `main` (ITK 6) | `ITK_FUTURE_LEGACY_REMOVE=ON` | nothing left that ITK will remove next |

ITK 6 always defines `ITK_LEGACY_REMOVE`. Under it, the deprecated `vnl/algo`
headers warn (`#warning`, or `#pragma message` on MSVC) and are no longer
included transitively from `itkMatrix.h`. Under `ITK_FUTURE_LEGACY_REMOVE`
they are `#error`, and 147 more headers drop their legacy API. A consumer that
merely compiles on ITK main with defaults is not done.

## Step 1: build both ITKs

In the forest kit, two forests give the two ITKs:

```bash
FOREST_REFERENCE_SUFFIX=itk-release-5.4 ITK_REF=upstream/release-5.4 pixi run checkout
FOREST_REFERENCE_SUFFIX=itk-release-5.4 pixi run build-ITK

FOREST_REFERENCE_SUFFIX=itk-main-future ITK_REF=upstream/main \
  ITK_FUTURE_LEGACY_REMOVE=1 FOREST_SCENARIO=itk-main pixi run checkout
FOREST_REFERENCE_SUFFIX=itk-main-future ITK_FUTURE_LEGACY_REMOVE=1 \
  FOREST_SCENARIO=itk-main pixi run build-ITK
```

Outside the kit, add `-DITK_FUTURE_LEGACY_REMOVE=ON` to an ITK main build.
Confirm by artifact: `itkConfigure.h` must contain
`#define ITK_FUTURE_LEGACY_REMOVE`.

## Step 2: build the consumer against each and collect the worklist

```bash
ninja -C <consumer-build> -k 0 2>&1 | tee build.log
grep -E 'error|is deprecated|deprecated:' build.log | sort -u
```

`-k 0` reports every failing translation unit in one pass. Build with MSVC as
well when you can: it does not reach headers transitively the way GCC and
Clang do, defaults to C++14, and lacks `M_PI`, so it finds problems the Unix
builds hide.

## Step 3: scan the source

```bash
python3 skills/itk-dual-version-compat/scan.py --itk-src ~/src/ITK <consumer-dir>
```

`scan.py` reads the deprecation table from the ITK checkout itself (every
header with `is deprecated; migrate to ...`), so it tracks ITK as it changes.
It reports `DEPRECATED_INCLUDE`, `DEPRECATED_SYMBOL` (usually reached through
an include ITK 6 no longer provides) and `MSVC_PORTABILITY`. On 2026-11-07 it
found 13 shims and 209 sites in ANTs plus BRAINSTools.

## Step 4: the rules for each fix

1. **Never include a deprecated header on the ITK 6 path.** Adding
   `#include "vnl/algo/vnl_svd.h"` makes the build compile again but brings
   back exactly the warning, and under FUTURE_LEGACY_REMOVE the error, this
   work is meant to remove.
2. **Detect the feature, not the version.** Select with
   `#if __has_include("itkBridgeMathSVD.h")`, so the code follows what the
   installed ITK provides. Use `ITK_VERSION_MAJOR` only where no header marks
   the change.
3. **One compat header per project; call sites stay unconditional.** Put the
   `#if` in a small header that defines a project-namespace function, and call
   that everywhere. Qualify it fully (`::ants::Determinant`) because ITK has
   its own `itk::ants` namespace.
4. **Keep the ITK 5 branch byte-for-byte the old code**, so 5.4 behavior
   cannot change. Include its headers explicitly in the `#else`.
5. **Match numerical semantics, then test both builds.** The replacements are
   Eigen-backed and differ in conventions (see the table).
6. **Include what you use.** `vnl_diag_matrix`, `vnl_determinant` and others
   stopped arriving transitively; a missing include is a bug, not an ITK one.
7. **Prefer ITK constants to platform macros:** `itk::Math::pi`, not `M_PI`.

| Deprecated | ITK 6 replacement | Notes |
|---|---|---|
| `vnl_svd`, `vnl_svd_fixed`, `vnl_svd_economy`, `vnl_matrix_inverse` | `itk::bridge::Math::SVD` (`itkBridgeMathSVD.h`) | `W` sorted descending; `PseudoInverse(rcond)`, `Solve`, `Rank`, `Recompose`, `RecomposeWith(w)`; `rcond < 0` picks n*eps |
| `vnl_determinant`, `vnl_det` | `itk::bridge::Math::Determinant` (`itkBridgeMathDeterminant.h`) | overloads for `itk::Matrix`, `vnl_matrix`, `vnl_matrix_fixed` |
| `vnl_symmetric_eigensystem` | `itk::bridge::SymmetricEigenDecomposition` | check eigenvalue order and vector sign convention |
| `vnl_real_eigensystem` | `itk::bridge::RealEigenDecomposition` | |
| `vnl_generalized_eigensystem` | `itk::bridge::GeneralizedEigenDecomposition` | |
| `vnl_qr` | `itk::bridge::QRDecomposition` | |
| `vnl_cholesky`, `vnl_ldl_cholesky` | `itk::bridge::Math::SolveSymmetricPositiveDefinite` / `CholeskyLowerTriangle` (`itkBridgeCholeskySolve.h`) | |
| `VNLSparseLUSolverTraits` | `SparseLUSolverTraits` (Eigen::SparseLU) | |

The scanner prints the current replacement text from ITK; trust it over this
table when they differ.

## Worked examples (ANTs and BRAINSTools, 2026-11-07)

A compat header for a function with several call sites:

```cpp
// Utilities/antsDeterminant.h
#if __has_include("itkBridgeMathDeterminant.h")
#  include "itkBridgeMathDeterminant.h"
#else
#  include "vnl/algo/vnl_determinant.h"
#endif
namespace ants
{
template <typename TMatrix>
auto
Determinant(const TMatrix & m)
{
#if __has_include("itkBridgeMathDeterminant.h")
  return itk::bridge::Math::Determinant(m);
#else
  return vnl_determinant(m);
#endif
}
} // namespace ants
```

A single-site rewrite where the semantics need care. `vnl_svd(A, -1e-6)` zeroes
singular values below 1e-6 of the largest; the bridge result keeps all of them,
so the threshold moves into the caller:

```cpp
#if __has_include("itkBridgeMathSVD.h")
  const auto                  svd = itk::bridge::Math::SVD(rotator);
  vnl_vector_fixed<double, 3> unitW(0.0);
  for (unsigned int i = 0; i < 3; ++i)
  {
    if (svd.W[i] > 1e-6 * svd.W[0])
    {
      unitW[i] = 1.0;
    }
  }
  return itk::Matrix<double, 3, 3>(svd.RecomposeWith(unitW));
#else
  // original vnl_svd code, unchanged
#endif
```

Other failures the same pass found, none specific to the ITK version but all
exposed by building on MSVC: `std::numeric_limits::infinity()` with no
template argument in an uninstantiated template, a lambda reading a `const`
local without capturing it (make it `static constexpr`), a project that sets
`CMAKE_CXX_STANDARD 14` (castxml then rejects ITK 6's C++17 deduction guides
while wrapping), and GCC-only flags such as
`-Wno-error=implicit-function-declaration` passed to every compiler.

## Done when

- [ ] Consumer builds with 0 errors against ITK `release-5.4`.
- [ ] Consumer builds with 0 errors against ITK main with
      `ITK_FUTURE_LEGACY_REMOVE=ON`.
- [ ] `grep -c 'is deprecated' build.log` is 0 for the main build.
- [ ] `scan.py` reports no `DEPRECATED_INCLUDE` outside the compat header's
      `#else` branch.
- [ ] The consumer's tests pass on both builds; numerical tests are compared,
      not just run.
- [ ] Commits follow the consumer's conventions; PRs open only after the user
      asks for them (`pr-no-unsolicited`).

## Provenance

Hans Johnson, 2026-11-07, while building the Windows forest: patches that
fixed ANTs and BRAINSTools on ITK main by including `vnl_determinant.h` and
`vnl_svd.h` "will require a set of #ifdefs", because ITK main deprecates those
headers. Asked for a skill to instrument code for building with
ITK/release-5.4 and with ITK/main with ITK_FUTURE_LEGACY_REMOVE=ON.
