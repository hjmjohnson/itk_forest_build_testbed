---
name: itk-deprecate-function
version: 1.0.0
purpose: Use when migrating an ITK numeric capability off VNL/VXL onto an Eigen-backed itk::Math::* implementation while keeping the old VNL call available through ITK's multi-version legacy-removal window, scavenging the VXL test suite into an ITK GoogleTest, and benchmarking Eigen vs VNL.
description: >-
  Use when deprecating a VNL/VXL function in ITK in favor of an Eigen-backed
  itk:: replacement. Drives the full pattern established by PR #6441 (PocketFFT
  default + deprecated vnl_fft_1d shim) and PR #6454 (itk::Math::MatrixExponential
  + restored vnl_matrix_exp shim): add the Eigen-backed itk:: API, restore the
  VNL symbol as an __has_include(<itkConfigure.h>)-gated three-state deprecation
  shim (silent default / ITK_LEGACY_REMOVE warning / ITK_FUTURE_LEGACY_REMOVE
  #error), scavenge the VXL test into an ITK GoogleTest, and benchmark Eigen vs
  VNL. Trigger on: "itk-deprecate-function", "/itk-deprecate-function",
  "deprecate vnl", "VNL to Eigen", "replace vnl_ with itk::Math", "Eigen backend
  for ITK", "scavenge vnl test", "vnl deprecation shim", "ITK_FUTURE_LEGACY_REMOVE".
triggers:
  - itk-deprecate-function
  - /itk-deprecate-function
  - deprecate vnl
  - VNL to Eigen migration
  - vnl deprecation shim
user_invocable: true
cmd: false
argument_hint: "<vnl_symbol> [e.g. vnl_matrix_exp | vnl_sparse_lu | vnl_fft_1d]"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "Modules/Core/Common/include/itkMath*.h"
      - "Modules/Core/Common/test/*GTest.cxx"
      - "Modules/ThirdParty/VNL/src/vxl/core/vnl/**"
      - "Documentation/docs/migration_guides/itk_6_migration_guide.md"
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
    - itk-convert-to-gtest
  external_tools:
    - git
    - cmake
    - ninja
  python_packages: []
  scripts: []
deployment:
  tier: always
  target_projects:
    - ITK
  needs_loader_dir: true
  adapters:
    - claude-code
---

# Deprecate an ITK function (VNL → Eigen)

## Quick reference

If invoked without a symbol, print this and ask which VNL symbol to deprecate:

```
itk-deprecate-function — Migrate a VNL/VXL numeric call onto an Eigen-backed
itk::Math:: implementation, keep the VNL symbol alive through ITK's legacy
window, scavenge the VXL test into an ITK GoogleTest, and benchmark.

Usage:
  /itk-deprecate-function vnl_matrix_exp     One symbol (see PR #6454)
  /itk-deprecate-function vnl_sparse_lu      Solver traits (current WIP branch)
  /itk-deprecate-function vnl_fft_1d         Algorithm family (see PR #6441)

Five phases (do not reorder):
  1. Scope        Find the VNL symbol, its VXL test, all ITK + downstream callers
  2. Eigen API    Add itk::Math::<X> (or *SolverTraits) delegating to Eigen
  3. Shim         Restore the VNL symbol as a 3-state deprecation bridge
  4. Test         Scavenge the VXL test into an ITK GoogleTest (same coverage)
  5. Prove+Report Gate: Eigen must beat VNL on BOTH accuracy AND speed;
                  post the proof as a PR comment. Pass => may run Eigen
                  behind the vnl_* API; fail => keep VNL engine.
```

## Intent (the durable direction)

ITK is moving its numeric base layer from **VNL/VXL to Eigen**. The goal is:
**Eigen is the algorithmic layer behind an `itk::` function call; the VNL call
is no longer exposed a few years from now.** This skill performs one symbol's
worth of that migration, the way PR #6441 and PR #6454 did.

Tracking issues: **#6403** (ITKv7 numerics direction), **#6230** (Eigen3
third-party design / no transitive Eigen exposure). Worked precedents:
**#6441** (`vnl_fft` → PocketFFT default + deprecated `vnl_fft_1d` alias),
**#6454** (`vnl_matrix_exp` → `itk::Math::MatrixExponential`). Current WIP:
`vnl_sparse_lu` → `EigenSparseLUSolverTraits`.

**The bar Eigen must clear (Phase 5 gate): better on _both_ accuracy and
speed.** Eigen replaces VNL only when proven superior on both axes — a faster
but less-accurate (or more-accurate but slower) Eigen path does not earn the
swap. The common and desired end-state is to **keep the `vnl_*` API but run the
Eigen algorithm behind it** once that proof exists (the #6441 `vnl_fft_1d`
model), so existing callers get the better engine transparently. The proof is a
written report posted to the PR (Phase 5).

### The three-state legacy policy (non-negotiable)

Every deprecated VNL symbol must honor ITK's three states. This is exactly the
guard PR #6454 shipped — reuse it verbatim (see Phase 3):

| State (CMake / compile define) | Behavior of the VNL symbol |
|---|---|
| **Default** (neither macro) — ITK 6 | Available, **silent**. The Eigen-backed `itk::` API is preferred but the VNL shim still compiles with no diagnostic. |
| **`ITK_LEGACY_REMOVE=ON`** (and not `ITK_LEGACY_SILENT`) | Available but emits a **deprecation `#warning`** (`#pragma message` on MSVC) pointing at the `itk::` replacement. |
| **`ITK_FUTURE_LEGACY_REMOVE`** | **Hard `#error`** — the symbol is not available to compile against. |

The Eigen-backed `itk::` API is **always** available in all three states; only
the VNL spelling is gated.

## Phase 1 — Scope the symbol

```bash
SYM="$1"   # e.g. vnl_matrix_exp
# 1a. The VNL declaration/definition in the vendored VXL tree
git -C "$ITK" grep -lE "\b${SYM}\b" -- 'Modules/ThirdParty/VNL/src/vxl/core/vnl/**'
# 1b. The original VXL test (the coverage to scavenge in Phase 4)
find "$ITK/Modules/ThirdParty/VNL/src/vxl" -path '*tests*' -iname "*${SYM#vnl_}*"
# 1c. ITK-internal callers (must keep compiling on the new API or the shim)
git -C "$ITK" grep -lE "\b${SYM}\b" -- 'Modules' ':!Modules/ThirdParty/VNL/**'
# 1d. Downstream callers (ANTs, BRAINSTools, elastix, Slicer) — drives whether
#     a shim is mandatory. PR #6454 kept vnl_matrix_exp because elastix includes
#     <vnl/vnl_matrix_exp.h>; #6441 kept vnl_fft_1d for ANTs N3.
```

Record: the VXL header path, the VXL test path, the analytic property the test
checks (e.g. skew-symmetric → rotation), and the downstream includers.

## Phase 2 — Add the Eigen-backed `itk::` API

Create `Modules/Core/Common/include/itkMath<Name>.h` (or a `*SolverTraits.h`),
`namespace itk { namespace Math { ... } }`, delegating to Eigen with a
**row-major `Eigen::Map` over the contiguous data block (no copy)**. Provide
overloads for `itk::Matrix`, `vnl_matrix_fixed`, and `vnl_matrix`. Pattern from
`itkMatrixExponential.h` (#6454):

```cpp
#include "itkeigen/unsupported/Eigen/MatrixFunctions"   // only if using an unsupported module
namespace itk::Math
{
namespace detail
{
template <unsigned int VRows, unsigned int VColumns, typename TReal>
void MatrixExponentialEigen(const TReal * inData, TReal * outData)
{
  using RowMajorMatrix = Eigen::Matrix<TReal, VRows, VColumns, Eigen::RowMajor>;
  Eigen::Map<const RowMajorMatrix> inMap(inData);
  Eigen::Map<RowMajorMatrix>       outMap(outData);
  outMap = inMap.exp();          // Eigen is the algorithmic layer
}
} // namespace detail
// public overloads for itk::Matrix / vnl_matrix_fixed / vnl_matrix forward here
}
```

Rules:
- **No transitive Eigen exposure** (#6230): Eigen types appear in a public
  signature only via an explicit opt-in template argument (as the solver-traits
  do), never leaked through a filter's default typedefs.
- If the Eigen capability lives in an **unsupported** module (MatrixFunctions,
  etc.), vendor the *whole module* intact under `itkeigen/unsupported/` and
  register it in `Modules/ThirdParty/Eigen3/UpdateFromUpstream.sh` so it
  survives the next Eigen re-sync (#6454 commit 1).
- Add a `.wrap` file for Python wrapping when the API is user-facing.

### Hunt for copy-elimination / wrong-conversion opportunities

When wiring Eigen in, actively look for places where data is needlessly
**copied into a vnl container** (or copied at all) when an `Eigen::Map` over the
existing contiguous storage — or a different/looser conversion — would be
cheaper and clearer. `Eigen::Map` aliases a raw `T*` block with zero copy; ITK
matrices/`vnl_matrix_fixed`/`vnl_matrix` all expose a contiguous block, so most
"build a vnl_matrix then hand it to the algorithm" patterns can become a
no-copy map.

Search patterns (ripgrep over the module and its callers):

```bash
# Existing Eigen::Map usage — study the idiom already in-tree, then mirror it
rg -n 'Eigen::Map<' Modules/
# Round-trips that materialize a vnl container just to feed an algorithm
rg -n 'vnl_matrix(_fixed)?<|vnl_vector<' <module> | rg -n 'copy|=\s*vnl_|\.set_|for\s*\('
# Element-by-element fills that could be one Map assignment
rg -n '\.put\(|\(\s*i\s*,\s*j\s*\)\s*=|data_block\(\)|begin\(\)\s*,\s*.*end\(\)' <module>
# Conversions between matrix families — candidates for Map instead of deep copy
rg -n 'GetVnlMatrix|as_matrix|as_ref|\.copy_in\(|\.copy_out\(|\.get\(.*\)' <module>
```

For each hit ask:
1. **Is a copy happening that a `Map` would remove?** A loop or constructor that
   reads a contiguous `T*` into a new matrix/vector → replace with
   `Eigen::Map<const RowMajorMatrix>(ptr, r, c)` (respect the storage order:
   ITK/vnl are row-major, Eigen defaults column-major, so spell `Eigen::RowMajor`
   as the wrappers above do).
2. **Is the conversion to a vnl type even necessary?** If the only consumer is
   the new Eigen algorithm, skip the vnl container entirely and map the source
   data directly; if a different ITK type (e.g. `itk::Matrix`) is already
   contiguous, map that instead of round-tripping through `vnl_matrix`.
3. **Does a looser conversion suffice?** Passing `const T*` + dims, an
   `Eigen::Ref`, or a `Map` by reference avoids both the copy and the type
   coupling — prefer the lightest one that compiles.

Record each opportunity; copy elimination here is often where the Eigen path's
speed margin (Phase 5) actually comes from, and removing a gratuitous vnl
conversion also shrinks the VNL surface being deprecated.

## Phase 3 — Deprecate the VNL symbol with a three-state guard

> **Rule — never remove the vendored VXL *API* without a three-stage
> deprecation route to an ITK-supported alternative. The *algorithm* may be
> replaced.** Distinguish two things:
>
> - **The API** (the `vnl_*` symbol / public class signature that downstreams
>   call directly when they include ITK as a convenience): MUST NOT be deleted
>   or renamed without the three-state deprecation guard below, and only once
>   an ITK-supported alternative exists. Renaming `VNL*SolverTraits.h` →
>   `Eigen*SolverTraits.h`, or deleting a `vnl_*` symbol outright, strands those
>   callers and discards the deprecation window — a process violation.
> - **The algorithm/implementation behind the API** (e.g. the vendored netlib
>   MINPACK `lmdif`/`lmder` sources backing `vnl_levenberg_marquardt`): MAY be
>   replaced, including by *auto-routing the kept API to the same Eigen
>   implementation the ITK-supported alternative uses* (the #6441 `vnl_fft_1d`
>   model). **Removing the outdated, poorly-performing netlib implementations is
>   an explicit goal** once the API is auto-routed and the gate (Phase 5) is
>   passed. Deleting the netlib sources is then correct — but verify they are
>   self-contained (no other vendored routine depends on them) and carry the
>   change through the VXL fork (`for/itk-vxl-master`) so the next
>   UpdateFromUpstream does not resurrect them.
>
> So: add the Eigen API alongside the VNL one (Phase 2), keep the VNL *API*
> spelling, re-back it on Eigen once proven, gate it with the guard below, and
> only then retire the dead netlib *engine* sources. (This skill exists partly
> because an early attempt deleted the *API* and had to be reverted; deleting
> the *implementation* after auto-routing is the intended end state.)

**Guard the API surface ITK actually exposes.** Two cases:

- **ITK wraps the vnl symbol in a class/traits** (e.g. `VNLSparseLUSolverTraits`
  wraps `vnl_sparse_lu`): guard the **ITK-facing header**, pointing at the Eigen
  replacement. Guarding the inner raw `vnl_*` header too would double-warn every
  internal includer — don't, unless downstreams include the raw header directly.
- **Downstreams include the raw `<vnl/<symbol>.h>` directly** (e.g. elastix and
  `vnl_matrix_exp`): guard the vnl header itself (#6454 model).

Prepend this guard (copy verbatim, change only the symbol and replacement
pointer). The `__has_include(<itkConfigure.h>)` gate keeps it inert for the
upstream VXL build (fires only for an ITK consumer). **`ITK_LEGACY_TEST` must be
in the opt-out** so ITK's own tests of the deprecated symbol don't break the
`ITK_LEGACY_REMOVE` CI build:

```cpp
#if __has_include(<itkConfigure.h>)
#  include <itkConfigure.h>
#  if defined(ITK_FUTURE_LEGACY_REMOVE)
#    error \
      "<symbol> was removed; migrate to <Replacement> (<header>, Eigen-backed)."
#  elif defined(ITK_LEGACY_REMOVE) && !defined(ITK_LEGACY_SILENT) && !defined(ITK_LEGACY_TEST)
#    if defined(_MSC_VER)
#      pragma message("<symbol> is deprecated; migrate to <Replacement>.")
#    else
#      warning "<symbol> is deprecated; migrate to <Replacement>."
#    endif
#  endif
#endif
```

Every ITK test that legitimately exercises the deprecated symbol must
`#define ITK_LEGACY_TEST` before the include (cross-checking the old vs new
engine is exactly such a test).

### Order of operations (a guard added too early breaks CI)

Add the guard **last**, only after ITK's own default consumers no longer use the
VNL spelling — otherwise ITK's `ITK_LEGACY_REMOVE` CI build emits the new
warning (and `-Werror` configs fail). The migration sequence that avoids this:

1. **Make internal consumers backend-neutral.** Route every backend-specific
   call through the *traits/abstraction*, not the concrete type — e.g. replace
   `matrix.mult(b, c)` (vnl-only) with `SolverTraits::MatVecMult(matrix, b, c)`,
   and ensure that method exists **symmetrically on both** the VNL and Eigen
   traits (add it where missing). A consumer that only touches the traits API
   works with either engine unchanged.
2. **Switch the consumers/tests to the Eigen traits** (the actual migration).
3. **Then** add the deprecation guard to the VNL spelling.

Commit ordering (mirror #6454): **(1) vendor Eigen module → (2) add itk:: API →
(3) restore VNL shim last**, so the shim's migration message points at an API
that already exists in the same series.

### Durable restore through the VXL fork

The in-place shim is the immediate bridge. The **same restore + identical
guard** must also be pushed to the VXL extraction branch
(`InsightSoftwareConsortium/vxl` `for/itk-vxl-master`) so the next VXL import
carries it through the sanctioned third-party channel (#6454 pushed
`e53123c57a`). Otherwise the next `UpdateFromUpstream` re-deletes the shim.

## Phase 4 — Scavenge the VXL test into an ITK GoogleTest

The VXL test found in Phase 1 defines the **algorithmic coverage** to preserve.
Re-express it as `Modules/Core/Common/test/itkMath<Name>GTest.cxx` exercising
the **`itk::` API** (not the VNL one), reproducing every analytic case plus
ITK-idiomatic edge cases. Use the `itk-convert-to-gtest` skill for the
mechanics. Structure (from `itkMatrixExponentialGTest.cxx`):

```cpp
#include "itkMathMatrixExponential.h"
#include <gtest/gtest.h>
TEST(MatrixExponential, RotationGenerator)   // scavenged from VXL test_matrix_exp
{
  // skew-symmetric generator g(t) -> rotation by t
  const auto result = itk::Math::MatrixExponential(g);
  EXPECT_NEAR(result(0, 0), std::cos(t), 1e-12);
  EXPECT_NEAR(result(0, 1), -std::sin(t), 1e-12);
  // ...
}
```

Coverage must include, at minimum: the original VXL analytic cases, identity/
zero, a degenerate case (nilpotent / singular), a large-norm or ill-conditioned
case, and `float` as well as `double`. Verify expected values against the real
computation, never transcribed from memory.

**Build and run the GTest locally before any push** (pr-local-test-first). Use a
configured build tree; the GTest links into `ITK<Module>GTestDriver`:

```bash
ninja -C <build> ITKCommonGTestDriver
ctest --test-dir <build> -R "<Name>" --output-on-failure
```

## Phase 5 — Prove Eigen is better (the gate), then choose the backend strategy

This phase is a **hard gate**, not a report. Eigen must beat VNL on **both
accuracy and speed** — *both*, not a trade-off. The benchmark's job is to make
that determination, and its outcome decides which deprecation strategy is even
allowed.

### The pass criteria (both must hold)

Measure Eigen and VNL on the **same** representative inputs (small / clinical
non-power-of-2 / large; well- and ill-conditioned). For every measured case:

1. **Accuracy — Eigen ≤ VNL error.** Compute a ground-truth-referenced error
   for each backend (round-trip residual `‖A·x − b‖/‖b‖` for a solver,
   `‖exp(A)·exp(−A) − I‖` for a matrix function, analytic reference where one
   exists). Eigen's error must be **≤** VNL's in every case, and strictly better
   in the ill-conditioned cases. A backend that is faster but *less* accurate
   **fails the gate**. Use a **relative, residual-based** error
   (`‖A·x − b‖/‖b‖`), not the forward error `‖x − x_exact‖`: an ill-conditioned
   system makes `‖x‖` huge for an arbitrary RHS, so a forward/absolute metric
   reads as a spurious "failure" even when both solvers are correct (their
   residuals are tiny). This bit the sparse-LU equivalence test until the metric
   was made relative.
2. **Speed — Eigen ≤ VNL time.** One backend at a time, median of N≥12 reps,
   **single-threaded** (`ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=1`) for a fair
   algorithm-vs-algorithm number, plus the as-shipped default if threading
   matters. Eigen's median must be **≤** VNL's (target: ≥ parity, ideally a
   speedup) across the swept sizes.

Methodology (from #6441): **build each backend against the ITK that provides
it** (VNL on `main`, Eigen on the branch) so the comparison is honest; **verify
by artifact, not pipe exit code** (`| tee` masks failures — confirm the
benchmark binary exists and ran). Present a markdown table (size ×
{VNL, Eigen [, reference]}) with **both** a time column and an error column,
lower = better, in the PR body under `<details>`.

### The decision the gate drives — does the `vnl_*` spelling get an Eigen engine?

| Gate outcome | Allowed deprecation strategy |
|---|---|
| **Eigen wins both accuracy and speed** | You may **back the `vnl_*` API with the Eigen algorithm** — keep the historical `vnl_*` spelling but swap its internals to delegate to the Eigen implementation, so *existing* `vnl_*` callers transparently get the better engine with no source change. This is the #6441 `vnl_fft_1d` model (the `vnl_fft_1d` spelling, PocketFFT engine, numerically equivalent, deprecated). The `vnl_*` symbol still carries the three-state guard (Phase 3) so it warns/`#error`s on schedule, but until then its *engine* is Eigen. State the proven margins in the shim's doc comment and the PR. |
| **Eigen ties or wins only one** (e.g. faster but less accurate, or vice-versa) | **Do NOT swap the `vnl_*` backend.** Leave the `vnl_*` symbol on its original VNL engine and add the Eigen implementation only as the **opt-in `itk::` API** (Phase 2). The deprecation shim restores/points at the VNL engine unchanged. Record the failing dimension so a later Eigen version can be re-evaluated. |
| **Eigen loses both** | Stop. Do not deprecate. The VNL function stays the implementation; revisit when Eigen improves. |

Backing the `vnl_*` API with Eigen is only earned by passing the gate. Until
proven, the historical `vnl_*` engine is preserved (this is also why Phase 3
*restores* removed VNL code rather than deleting it — never strand callers on a
worse or unproven engine).

### Equivalence requirement when you do swap the backend

If the gate passes and you back `vnl_*` with Eigen, the swapped engine must be
**numerically equivalent** to the original within the API's contract (e.g.
#6441's `vnl_fft_1d` preserves the vnl sign convention and is exact at the
printed precision; round-trip ≈ 2e-15). Add an equivalence test (old-vs-new on
the same inputs) to the scavenged GoogleTest. Compare the two engines by
**relative** agreement (`‖x_old − x_new‖ / ‖x_old‖`), not an absolute
difference — for an ill-conditioned operator the solutions are legitimately
large, so an absolute tolerance flags a false divergence while the relative
agreement stays tight. Mark such tests `#define ITK_LEGACY_TEST` so they don't
trip the deprecation warning they include.

### The performance proof is a report posted to the PR (required)

The gate determination must be written up as a **performance-proof report and
included as a PR comment** (and summarized under a `<details>` block in the PR
body). The PR is not ready for review until that report is posted. The report
is the durable evidence that the both-accuracy-and-speed gate was met — a
reviewer must be able to read it without re-running anything.

The report must contain:

- **Verdict line up top:** e.g. *"Eigen passes the gate: faster in N/N sizes,
  equal-or-better accuracy in N/N — backend swap of `vnl_*` is justified."* or
  the corresponding fail verdict.
- **Two-axis table:** size/condition × backend, with **both** a time column
  (median ms, lower better) **and** an error column (residual/round-trip),
  Eigen and VNL side by side. Mark every cell where Eigen ≤ VNL.
- **Environment:** OS, compiler, CPU, thread setting, reps, and the ITK ref each
  backend was built against (VNL on `main`, Eigen on the branch).
- **Reproducer:** the benchmark source/target and the exact command, so the
  numbers can be regenerated.

Post it with `gh pr comment <N> --body-file <report.md>` (use `--body-file`,
not inline). Keep the visible PR body short per pr-message-format; the full
table lives in the comment and a `<details>` block. Encode the verdict and key
margins in an HTML comment for future sessions.

## Pre-flight & commit discipline

- Work on a fresh branch off latest `upstream/main`.
- One logical commit per layer (vendor / api / shim / test), `COMP:`/`ENH:`
  prefixes; the test may be its own `ENH:` commit.
- `pre-commit run --all-files` must exit 0 before any push
  (pre-commit-mandatory).
- **No PR without explicit human approval** (pr-no-unsolicited); when asked,
  `--draft` only, body per pr-message-format with the perf table in `<details>`.
- Cross-reference the tracking issues (#6403, #6230) and the precedent PRs
  (#6441, #6454) in the PR body.

## Quality checklist

- [ ] Eigen-backed `itk::` API added, no-copy `Eigen::Map`, overloads for
      itk::Matrix / vnl_matrix_fixed / vnl_matrix
- [ ] Hunted callers for needless vnl conversions / copies that an `Eigen::Map`
      (or a looser/no conversion) replaces; recorded or applied each
- [ ] No transitive Eigen exposure (#6230) — opt-in template arg only
- [ ] Unsupported Eigen module (if any) vendored whole + registered in
      UpdateFromUpstream.sh
- [ ] **VNL API kept, never deleted/renamed without the 3-state guard + an ITK-supported alternative** — Eigen added alongside; the kept API may be auto-routed to the Eigen impl, but the *symbol/signature* is not removed out from under direct callers
- [ ] **Dead netlib *implementation* sources retired only after auto-routing + gate pass** — confirmed self-contained (no other vendored routine depends on them), removed from the third-party build, and carried through the VXL fork (`for/itk-vxl-master`)
- [ ] Internal consumers made backend-neutral (route through the traits/abstraction; method added symmetrically to both traits) and migrated to Eigen **before** the guard
- [ ] Guard placed on the ITK-facing API surface; honors `ITK_LEGACY_TEST`; internal tests of the deprecated symbol `#define ITK_LEGACY_TEST`
- [ ] All three guard states verified (silent / warning / error)
- [ ] VNL shim restored with the verbatim `__has_include`-gated three-state guard
- [ ] Guard inert during ITK's own VXL build (only fires for consumers)
- [ ] Same restore + guard pushed to `vxl` `for/itk-vxl-master`
- [ ] VXL test scavenged into an ITK GoogleTest with equal-or-greater coverage
- [ ] GTest built and run locally (green) before push
- [ ] **Phase 5 gate met: Eigen ≤ VNL error AND Eigen ≤ VNL time in every measured case** (both axes — not a trade-off)
- [ ] Backend strategy chosen by the gate: `vnl_*` engine swapped to Eigen **only** if the gate passed; otherwise VNL engine preserved and Eigen offered opt-in
- [ ] If backend swapped: numerical-equivalence (old-vs-new) test added to the GoogleTest
- [ ] **Performance-proof report posted as a PR comment** (`--body-file`) with verdict line, two-axis (time + error) table, environment, and reproducer
- [ ] Commit order: vendor → api → shim(last); pre-commit clean; draft PR only on request

## Worked references

- **PR #6441** — `vnl_fft` → PocketFFT default; `vnl_fft_1d` restored as a
  deprecated PocketFFT-backed alias. Canonical for the alias + benchmark table.
- **PR #6454** — `vnl_matrix_exp` → `itk::Math::MatrixExponential`. Canonical
  for the three-state guard, whole-module Eigen vendoring, and the GTest scavenge.
- **WIP branch `lu-eigen-sparse-traits`** — `vnl_sparse_lu` →
  `EigenSparseLUSolverTraits` (solver-traits variant; Solve() returns
  Eigen::Success, MatVecMult added for consumers).
