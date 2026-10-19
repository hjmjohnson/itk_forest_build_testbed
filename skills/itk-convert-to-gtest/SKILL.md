---
name: itk-convert-to-gtest
version: 1.4.0
purpose: Mechanically convert no-argument ITK CTests in one module to GoogleTest, one test per commit, preserving behavior and git history, following N-Dekker's "one commit, one change" reviewer standard.
description: Convert no-argument ITK CTests (itk_add_test with no trailing args) to GoogleTest format. Strictly mechanical, one test per git-mv-tracked commit, with assertion-macro mapping, CMakeLists rewiring, and mandatory per-commit build+test. Use when migrating an ITK module's legacy CTest functions to the GTest driver.
triggers:
  - itk-convert-to-gtest
  - /itk-convert-to-gtest
  - convert to gtest
  - ctest to googletest
  - convert ITK test to GoogleTest
user_invocable: true
cmd: false
argument_hint: "[Modules/Group/Name | <test-dir>]"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "Modules/**/test/*.cxx"
      - "Modules/**/test/CMakeLists.txt"
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: true
    network_required: false
    git_required: true
    user_confirmation_required: true
  determinism: deterministic
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
  external_tools:
    - git
    - python3
    - clang-format
    - ninja
    - cmake
    - llvm-cov
    - llvm-profdata
  python_packages: []
  scripts:
    - find_gtest_candidates.py
    - coverage/configure_coverage_build.sh
    - coverage/run_coverage_tests.sh
    - coverage/export_per_driver.sh
    - coverage/map_profile_signatures.sh
    - coverage/compare_coverage.py
    - coverage/per_test_coverage.py
    - coverage/classify_per_test.py
    - coverage/repeat_pairs.py
    - coverage/rerun_variability.sh
deployment:
  tier: project
  target_projects:
    - itk
  needs_loader_dir: true
  adapters:
    - claude-code
---

# Convert ITK CTests to GoogleTest

Convert all no-argument CTests in a module's `test/` directory to GoogleTest
format. Process **one test at a time**, with a separate git commit for each
conversion. This skill replaces the legacy `convert-to-gtest` command.

## Quick reference

If invoked without arguments, print this and operate on `./test/`:

```
itk-convert-to-gtest — Mechanical CTest -> GoogleTest, one commit per test

Usage:
  /itk-convert-to-gtest Modules/Core/Common   Convert that module's test/ dir
  /itk-convert-to-gtest                        Convert ./test/ in the cwd

Discovery only (no edits):
  python3 find_gtest_candidates.py <itk-root> --json   Whole-tree inventory
  python3 find_gtest_candidates.py . --module Modules/Core/Common
```

## Core philosophy: mechanical conversion only

> "One Commit One Change" — N-Dekker, ITK reviewer

The conversion must be **strictly mechanical**. The GTest file must behave
identically to the old test. Do **not**:

- Remove existing comments (especially scope-explaining comments)
- Add `[[maybe_unused]]` unless a variable is genuinely never read
- Refactor, simplify, or restructure logic beyond what conversion requires
- Add diagnostic output that was not in the original

The reviewer standard: "Please just do Test-to-GoogleTest conversion."

## Step 1: Discover no-argument tests

Run the packaged scanner against the target module:

```bash
python3 find_gtest_candidates.py "$ITK_ROOT" --module Modules/Group/Name
```

A candidate is an `itk_add_test` whose `NAME` equals its test function and has
**no arguments** after the function name:

```cmake
itk_add_test(
  NAME itkFooTest
  COMMAND
    ITKThisModuleTestDriver
    itkFooTest
)
```

The scanner skips tests that pass arguments (files, numbers, paths) after the
function name, and skips any whose `*GTest.cxx` already exists.

It also **excludes**, with a reason (listed under `excluded` in `--json`),
tests that a mechanical conversion would change:

| Reason | Why it cannot be converted mechanically |
|---|---|
| `test-properties` | Named in `set_tests_properties` (ENVIRONMENT, WILL_FAIL, and so on); those settings do not carry over to a GoogleTest case. |
| `function-reused` | The same test function is also registered with arguments; the `.cxx` must stay. |
| `factory-dependent` | Enumerates, unregisters, or registers object factories. The legacy driver registers every IO/FFT factory before each test; GoogleTest drivers register none, so the converted test would run against an empty factory list. |

Tests registered inside `if(0)`, `if(FALSE)`, or a similar disabled block are
**converted, not skipped**, and listed under `disabled`. Such blocks exist for
many reasons and often mark unfinished work that needs future investigation,
so the conversion must keep the test disabled and keep every comment around
the block. See 2d for the CMake form.

Two more skip reasons the scanner cannot detect; check for them when reading
the test (2a) and skip, recording why:

- the test calls helpers (`println()`, `GetTestImage()`, ...) defined in a
  *different* legacy test file that stays in the legacy driver;
- the test's pass/fail depends on a helper's exit code meaning "the expected
  exception happened", which `EXPECT_*` cannot express without restructuring.

## Step 2: For each candidate — convert one file at a time

Work through candidates one at a time. For each `itkFooTest`:

### 2a. Read the old test file

Read `itkFooTest.cxx` carefully. Understand **every** check, output statement,
and comment — all must be preserved in the new file.

### 2b. Rename with `git mv` (MANDATORY — preserves history)

Rename **before** editing contents so `git log --follow` tracks the history:

```bash
git mv Modules/Path/To/test/itkFooTest.cxx Modules/Path/To/test/itkFooGTest.cxx
```

Git detects renames by content similarity; creating a new file from scratch
severs history. If too many edits break rename detection, commit the rename
first, then the content edits as a fixup.

### 2c. Edit `itkFooGTest.cxx`

- Include the primary header being tested first.
- Use `#include "itkGTest.h"` (not `<gtest/gtest.h>`).
- Use `ITK_GTEST_EXERCISE_BASIC_OBJECT_METHODS(ptr, ClassName, SuperclassName)`
  (from `itkGTest.h`) wherever `ITK_EXERCISE_BASIC_OBJECT_METHODS` was used.
  It requires a **named pointer variable**, not an inline `New()` expression.
- Wrap helper functions **and helper classes** in an anonymous
  `namespace { }`. Do not keep a legacy `namespace itk { }` around test
  helpers: in a shared GoogleTest driver, external linkage risks an ODR clash
  with another test's helper of the same name.
- Preserve `std::cout` diagnostics **only** when they call functions that would
  otherwise not be exercised; otherwise minimize redundant output on pass.
- Preserve all comments, especially scope-explaining ones.
- Legacy-API tests: wrap in `#ifndef ITK_FUTURE_LEGACY_REMOVE` / `#endif`.

#### Test name convention

Use `TEST(ClassName, ConvertedLegacyTest)` for a converted test with no finer
logical subdivision. Split into multiple `TEST()` blocks **only** if the
original already had clearly distinct logical sections.

#### Assertion mapping

Translate output/return-code checks into the **most specific** macro:

| Original pattern | GTest equivalent |
|---|---|
| `if (!condition) return EXIT_FAILURE` | `EXPECT_TRUE(condition)` |
| `if (a != b) return EXIT_FAILURE` | `EXPECT_EQ(a, b)` |
| `if (a == b) return EXIT_FAILURE` | `EXPECT_NE(a, b)` |
| `if (a <= b) return EXIT_FAILURE` | `EXPECT_GT(a, b)` |
| `if (a >= b) return EXIT_FAILURE` | `EXPECT_LT(a, b)` |
| `if (ptr == nullptr) return EXIT_FAILURE` | `EXPECT_NE(ptr, nullptr)` |
| `if (ptr != nullptr) return EXIT_FAILURE` | `EXPECT_EQ(ptr, nullptr)` |
| `ITK_TRY_EXPECT_EXCEPTION(expr)`, or a try/catch that prints the caught expected exception | `ITK_GTEST_EXPECT_THROW_AND_PRINT(expr, ExceptionType)` |
| try/catch expecting an exception, without printing it | `EXPECT_THROW(expr, ExceptionType)` / `ASSERT_THROW` |
| comparing ITK array-like objects | `ITK_EXPECT_VECTOR_NEAR(v1, v2, rmsError)` |

#### Keep printing caught exceptions

`ITK_TRY_EXPECT_EXCEPTION` prints the exception it catches, and many tests
print a caught exception explicitly. That print runs the exception's `Print`
code, and for an exception carrying a DataObject (`InvalidRequestedRegionError`)
the object's whole `PrintSelf` chain. Plain `EXPECT_THROW` prints nothing, so
it silently drops that coverage: about 160 lines in one test in the 2026-10
staging run. Use `ITK_GTEST_EXPECT_THROW_AND_PRINT(statement, ExceptionType)`
from `itkGTest.h` wherever the original printed the caught exception.

The macro is added by the commit "ENH: Add ITK_GTEST_EXPECT_THROW_AND_PRINT
GoogleTest macro" (branch `gtest-expect-throw-and-print` until it lands
upstream). Any conversion branch must be based on that commit.

#### `EXPECT_*` by default, `ASSERT_*` only when later code depends on it

Prefer `EXPECT_*`: it reports every failure in one run. Use `ASSERT_*` only
when a later statement would be unsafe or meaningless if the check failed,
typically a null check before a dereference:

```cpp
ASSERT_FALSE(clone.IsNull());          // the next line dereferences clone
auto field = clone->GetDisplacementField();
```

With `EXPECT_*` there, a null clone records a failure and then segfaults,
turning a readable failure into a crash. Matching the original's early
`return EXIT_FAILURE` is not by itself a reason for `ASSERT_*`.

#### `EXPECT_TRUE` is the assertion of last resort

When the predicate inside `EXPECT_TRUE(...)` is itself a comparison or a helper
wrapping `==`, rewrite to a binary `EXPECT_*` macro so the failure prints the
operands. Apply during the initial conversion, not as review feedback.

| Don't write | Write instead |
|---|---|
| `EXPECT_TRUE(a == b)` | `EXPECT_EQ(a, b)` |
| `EXPECT_TRUE(a != b)` | `EXPECT_NE(a, b)` |
| `EXPECT_TRUE(a < b)` / `<=` / `>` / `>=` | `EXPECT_LT/LE/GT/GE(a, b)` |
| `EXPECT_TRUE(ptr == nullptr)` | `EXPECT_EQ(ptr, nullptr)` |
| `EXPECT_TRUE(itk::Math::ExactlyEquals(a, b))` | `EXPECT_EQ(a, b)` |
| `EXPECT_TRUE(itk::Math::AlmostEquals(a, b))` | `EXPECT_DOUBLE_EQ(a, b)` (or `EXPECT_FLOAT_EQ`) |

`EXPECT_TRUE` is reserved for genuinely-boolean predicates
(`EXPECT_TRUE(ptr->IsValid())`, `EXPECT_TRUE(container.empty())`). The same
rule applies to `ASSERT_TRUE`. Only add assertions corresponding to a real
check in the original — never invent assertions.

#### Match literal signedness in `EXPECT_EQ`/`ASSERT_EQ`

When an `if (a != b)` check converts to `EXPECT_EQ(a, b)` and one operand is an
**unsigned** expression (`.size()`, `.GetNumberOfComponents()`,
`GetIndexDimension()`, `rank()`, `itk::Math::Absolute(int)`, container counts)
while the other is a **signed** integer literal, GCC `-Wextra` emits
`-Wsign-compare` from inside GoogleTest's `CmpHelperEQ` template. It is
attributed to the test `.cxx` and is *not* suppressed by gtest's `-isystem`
include (template-instantiation warnings surface at the instantiation site).
Match the literal's signedness at conversion time so it never re-surfaces:

| Don't write | Write instead |
|---|---|
| `EXPECT_EQ(v.size(), 0)` | `EXPECT_EQ(v.size(), 0u)` |
| `EXPECT_EQ(3, obj->GetNumberOfComponents())` | `EXPECT_EQ(3u, obj->GetNumberOfComponents())` |

In a helper or `TEST` template body instantiated for **both** signed and
unsigned element types, a bare `u` suffix only moves the warning to the signed
instantiation — cast the literal to the operand type instead:
`EXPECT_EQ(pt.back(), static_cast<std::decay_t<decltype(pt.back())>>(7))`. For a
signed `std::count(...)` result compared with an unsigned `size`, cast the
count: `static_cast<std::size_t>(std::count(...))`.

Template:

```cpp
/*=========================================================================
 *  Copyright NumFOCUS
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *=========================================================================*/

// First include the header file to be tested:
#include "itkFoo.h"
#include "itkGTest.h"

namespace
{
// helper functions here
} // namespace

TEST(Foo, ConvertedLegacyTest)
{
  // test body with EXPECT_* assertions mirroring the original checks
}
```

### 2d. Update `CMakeLists.txt`

Three edits, keeping every `set()`/`list(APPEND)` source list **alphabetically
sorted**:

1. **Remove** the `.cxx` from the legacy `ITKThisModuleTests` `set(...)` block.
2. **Remove** the entire `itk_add_test(...)` block.
3. **Add** the new `*GTest.cxx` to the `ITKThisModuleGTests` `set(...)` block at
   its correct alphabetical position.

The `ITKThisModuleGTests` set feeds
`creategoogletestdriver(ITKThisModuleGTests ...)` which builds
`ITKThisModuleGTestDriver`.

#### A test inside a disabled block (`if(0)`, `if(FALSE)`, ...)

Convert it, but keep it disabled with the same condition and **every comment**
that explained the block. The GoogleTest equivalent of a disabled
registration is a disabled entry in the GoogleTest source list, so move the
block (comments included) to sit after the `ITKThisModuleGTests` `set(...)`
and before `creategoogletestdriver(...)`:

```cmake
# Before (legacy, among the itk_add_test calls):
#
# This test should be enabled if you suspect that the memory leak detector
# is not working
if(0)
  itk_add_test(NAME itkMemoryLeakTest COMMAND ITKCommon2TestDriver itkMemoryLeakTest)
endif()

# After (immediately before creategoogletestdriver):
#
# This test should be enabled if you suspect that the memory leak detector
# is not working
if(0)
  list(APPEND ITKCommonGTests itkMemoryLeakGTest.cxx)
endif()
creategoogletestdriver(ITKCommon "${ITKCommon-Test_LIBRARIES}" "${ITKCommonGTests}")
```

Remove the `.cxx` from the legacy source list as usual. A GoogleTest source
inside `if(0)` is not compiled, whereas the legacy `.cxx` usually was, so
before committing, **temporarily change the condition to `if(1)`**, build the
GoogleTest driver, run the test, then restore the original condition. Rebuild
the driver afterward and confirm `ctest -N -R '^Suite\.'` lists no test,
because GoogleTest cases are discovered from the last-built driver.

### 2e. Verify the rename was tracked

```bash
git status Modules/Path/To/test/    # should show "renamed", not delete+add
```

If shown as delete+add, the edits changed too much — commit the rename alone
first, then the content edits as a fixup. **Never** use `git rm` + `Write`.

### 2f. Commit

```bash
git add Modules/Group/Name/test/itkFooGTest.cxx \
        Modules/Group/Name/test/CMakeLists.txt
git commit -m "ENH: Convert itkFooTest to GoogleTest"
```

Use that subject form for every test so batches read uniformly. The
commit-msg hook rejects subjects of 78 characters or more; for a long test
name use `ENH: Convert <Foo> test to GoogleTest` (drop `itk` and `Test`,
abbreviate further if needed) and put `Converts itkFooTest.` in the body. Run
`pre-commit run --all-files` before committing; if clang-format/gersemi
reformat staged files, re-stage and commit again.

### 2g. Build and test (MANDATORY)

After **each** commit, build and run the converted test before the next
candidate. Do not batch verification to the end.

```bash
cmake --build build --target ITKThisModuleGTestDriver -j"$(getconf _NPROCESSORS_ONLN)"
ctest --test-dir build -R "itkFooGTest" --output-on-failure
```

Pixi workflow:

```bash
pixi run --as-is ctest -R "itkFooGTest" --output-on-failure
```

If the build or test fails, fix and amend the commit before proceeding.

### 2h. Coverage parity (MANDATORY per batch, before a PR)

Passing tests do not show the conversion exercises the same code. Before a
batch goes up for review, prove coverage parity with the packaged scripts in
`coverage/` (LLVM source-based coverage; see `coverage/README.md`):

1. Two coverage builds with the same modules: the base, and the batch.
2. **Per test:** each old CTest alone vs its GoogleTest alone. Every library
   line the original covered must be covered by the conversion, after
   subtracting the legacy driver's startup overhead (measured exactly by
   running the driver with an unknown test name) and excluding TestKernel.
   `classify_per_test.py` assigns any residual to an explained category
   (factory environment, exception printing, check helper) or flags it.
3. **Aggregate:** line-by-line comparison of all modules, three steady-state
   runs per side (`compare_coverage.py`), which must report 0 lost lines.

Re-run flagged pairs with `repeat_pairs.py`; only losses stable across runs
count. A real loss means the conversion dropped something: fix it or skip the
test.

## Step 3: Augmenting existing GTest files

If a `*GTest.cxx` already exists, **append** new `TEST()` blocks rather than
creating a file. Read the existing file first to avoid duplicating coverage,
then follow steps 2c–2e.

## Common pitfalls

- `ITK_GTEST_EXERCISE_BASIC_OBJECT_METHODS` needs a named pointer in scope, not
  an inline `New()` expression.
- Double braces for aggregate-initialized ITK structs: `itk::Size<3> sz{ { 10, 10, 10 } };`.
- `[[maybe_unused]]` only when a variable is genuinely never read.
- `std::hash` is implementation-defined — never assert `hash(x) == x`.
- Avoid platform-specific numeric assumptions in assertions.
- Do **not** add a `main()` — GTest provides its own.
- Do **not** use `EXIT_SUCCESS`/`EXIT_FAILURE` returns — use `EXPECT_*`/`ASSERT_*`.
- Do **not** wrap a comparison in `EXPECT_TRUE` — use the matching binary macro.
- Match literal signedness in `EXPECT_EQ`/`ASSERT_EQ` against unsigned getters
  (`size()`, counts, dimensions): write `0u`/`3u`, or
  `static_cast<std::decay_t<decltype(expr)>>` in mixed-signedness template
  bodies, so converted tests do not re-introduce `-Wsign-compare`.
- Do **not** combine multiple CTest files into one `*GTest.cxx`.
- Do **not** remove scope-explaining comments.
- The old driver called `itkFooTest(int argc, char* argv[])`; the GTest file is
  standalone and must not define that signature.
- Always use `git mv`, never `git rm` + new file.
