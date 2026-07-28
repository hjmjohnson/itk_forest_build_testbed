---
pattern: equals-default-special-members
clang_tidy_check: modernize-use-equals-default
itk_main_status: merged
itk_main_ref: bc66259, b21dbbb
scope: downstream-and-new-code
---

## Overview

Replace hand-written **empty-body** special members with `= default`. An
explicit `Foo() {}` or `~Foo() {}` is *user-provided* — the compiler treats it
as non-trivial and (for the destructor) suppresses the implicit move
constructor/assignment. `= default` restores triviality and move semantics and
makes intent obvious. This is one of ITK's largest modernization campaigns
(51+ commits) and pairs the stock `modernize-use-equals-default` check with a
supplementary out-of-line empty-destructor pass.

**Core principle:** only an *genuinely empty* body converts. A body with any
statement — or a comment that hides code — is not a candidate.

## When to use

- In-class empty special members: `Foo() {}`, `~Foo() override {}`,
  `virtual ~Foo() {}`.
- Out-of-line empty destructor definitions: `Foo::~Foo() {}` /
  `Foo::~Foo()\n{}` in a header/`.hxx` — the declaration becomes
  `~Foo() override = default;` and the empty out-of-line body is deleted.

## When NOT to use

- **Polymorphic destructor that must stay out-of-line for ABI** (exported
  class, `-fvisibility-inlines-hidden`, hidden `D1Ev`/`D0Ev` symbols). Defer to
  `itk-inline-destructors-fix`; do NOT inline it here.
- Body is not empty (any statement, even a single call/log line).
- Body "looks" empty but contains a comment that is really commented-out code,
  or a `static_assert`/macro that expands to statements.
- ThirdParty/ trees (excluded by `detect.sh`).

## Before / after

```cpp
// before
class ArrivalFunctionToPathCommand
{
  ArrivalFunctionToPathCommand() {}
  ~ArrivalFunctionToPathCommand() override {}
};

// after
class ArrivalFunctionToPathCommand
{
  ArrivalFunctionToPathCommand() = default;
  ~ArrivalFunctionToPathCommand() override = default;
};
```

Out-of-line case:

```cpp
// before (in the .hxx)
template <typename T> Foo<T>::~Foo() {}
//        and the in-class declaration:  ~Foo() override;

// after — delete the out-of-line body, default the declaration:
//        ~Foo() override = default;
```

## Detection

```bash
bash skills/itk-equals-default-special-members/detect.sh [repo-path]
```

Greps (via `git grep`, ThirdParty/ excluded) for in-class empty-body special
members `Name(...) [override] {}` and out-of-line `T::~T() {}` /
`T::~T()\n{}`. Prints `file:line` hits and a total count.

## Transformation approach

Two passes. The in-class `{}` → `= default` case is safely automatable with
the upstream clang-tidy check; the out-of-line case is review-only.

1. **In-class (automatic) — clang-tidy:**
   ```bash
   clang-tidy -p <build-with-compile_commands.json> \
       -checks='-*,modernize-use-equals-default' \
       --fix <file.h ...>
   ```
   Requires a `compile_commands.json`; the check verifies the body is empty
   before converting, so it will not touch non-empty bodies.

   clang-query matchers that identify the same sites (for auditing):
   ```
   cxxConstructorDecl(isDefaultConstructor(),
       hasBody(compoundStmt(statementCountIs(0))))
   cxxDestructorDecl(hasBody(compoundStmt(statementCountIs(0))))
   ```

2. **Out-of-line empty destructor (review-only):** convert
   `T::~T() {}` to `~T() override = default;` at the in-class declaration and
   delete the out-of-line body. This is NOT auto-applied because the
   declaration and definition live apart (often different files) and because a
   polymorphic dtor may need to stay out-of-line for ABI. `detect.sh` flags
   these as `[out-of-line]`; resolve each by hand, deferring exported-class
   cases to `itk-inline-destructors-fix`.

## Verification (pattern-specific)

For exported classes, confirm no hidden-symbol/ABI regression was introduced
(run `itk-inline-destructors-fix`'s audit if in doubt).

## Common mistakes

- **Inlining a polymorphic out-of-line dtor that must stay out-of-line** for
  shared-library visibility — breaks ABI. Defer to `itk-inline-destructors-fix`.
- Converting a body that is not actually empty (statement hidden by a macro, or
  commented-out code). Read each hit; clang-tidy guards the in-class case but
  the out-of-line manual pass does not.
- Running clang-tidy without a `compile_commands.json` for the right config —
  the fix silently no-ops.
- Sweeping ThirdParty/ — never modernize vendored code (`detect.sh` excludes it).
