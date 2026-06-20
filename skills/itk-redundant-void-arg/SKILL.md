---
name: itk-redundant-void-arg
description: >-
  Use when removing the redundant `(void)` argument list from C++ function
  declarations and definitions in ITK and ITK-ecosystem sources (ANTs,
  BRAINSTools, SlicerExecutionModel, remote modules) — the C-ism
  `StartOptimization(void) override;` that should be `StartOptimization()`.
  Covers methods, free functions, and out-of-line definitions like
  `SpeedFunctionPathInformation<TPoint>::Advance(void)`. Trivially mechanical,
  zero behavioral risk. Must NOT touch function-pointer typedefs, `extern "C"`
  blocks, or real C headers where `(void)` is semantically required. Keywords:
  modernize-redundant-void-arg, redundant void, (void) argument, empty
  parameter list, C-ism cleanup, void parameter removal, clang-tidy modernize.
---

> **Constraint — C++17, ITKv5 + ITKv6:** target C++17 idioms valid against both ITK >=5.4 and ITKv6; never require C++20+. Verify transformed output by compiling against both ITK header sets with `-std=c++17` (see skills/BRAINSTOOLS_HARDENING.md).

# itk-redundant-void-arg

## Overview

In C++ an empty parameter list `()` already means "takes no arguments"; the
explicit `(void)` is a C-ism that adds noise. Removing it is purely
syntactic — same overload, same ABI, same behavior.

**Core principle:** prefer the clang-tidy check `modernize-redundant-void-arg`
over `sed`. The check understands the AST and safely **skips** the sites where
`(void)` is meaningful — function-pointer typedefs and C-interop declarations —
which a textual substitution cannot distinguish.

## When to use

- Cleaning long-lived C++ sources that carry `(void)` parameter lists on
  methods/functions (common in older ANTs / BRAINSTools / ITK code).
- A style-only pass with no logic change; safe to batch across a module.

## When NOT to use

- `extern "C"` blocks and real C headers (`.c`, C-only `.h`) — there `(void)`
  IS required to declare a no-arg prototype; removing it changes C semantics.
- Function-pointer typedefs (`typedef void (*fn)(void);`) — leave as-is.
- ThirdParty/ vendored trees — never modernize imported upstream code.

## Before / after

```cpp
- void StartOptimization(void) override;
+ void StartOptimization() override;

- SpeedFunctionPathInformation<TPoint>::Advance(void)
+ SpeedFunctionPathInformation<TPoint>::Advance()
```

## Detection

```bash
bash skills/itk-redundant-void-arg/detect.sh <repo-path>   # default .
```

Greps tracked `*.h *.hxx *.cxx *.cpp *.cc` (excluding `ThirdParty/`) for an
identifier immediately followed by `(void)`, prints `file:line` hits and a
count. Function-pointer typedef lines and `extern "C"` are likely false
positives — the count is a candidate upper bound; clang-tidy is the arbiter.

## Transformation approach (clang-tidy, preferred)

Requires a `compile_commands.json` (any configured CMake build with
`CMAKE_EXPORT_COMPILE_COMMANDS=ON`).

```bash
clang-tidy -p <build-dir> \
    --checks='-*,modernize-redundant-void-arg' --fix \
    $(git -C <repo> ls-files '*.h' '*.hxx' '*.cxx' '*.cpp' '*.cc' \
        | grep -v '/ThirdParty/' | sed "s#^#<repo>/#")
```

The check leaves function-pointer typedefs and C-interop `(void)` untouched.
After fixing, rebuild the affected module to confirm the tree still compiles,
then `git diff` to confirm only `(void)` -> `()` edits landed.

`transform.sh` provides a sed fallback for environments without a compilation
database. It is **dry-run by default**, `--apply` to write, and never commits.
The sed fallback is review-only: it cannot distinguish C-interop sites, so
inspect every hunk before applying and exclude `extern "C"` regions manually.

## Verification

- `git diff` shows only `(void)` -> `()` changes.
- The module rebuilds (clang-tidy fixes are syntactic; a clean build confirms
  no typedef/C-interop site was wrongly rewritten).
- `detect.sh` re-run reports a lower count (remaining hits are the legitimate
  function-pointer / C-interop sites).

## Common mistakes

- Running `sed` blindly — strips `(void)` from function-pointer typedefs and
  `extern "C"` prototypes, breaking C interop. Use clang-tidy.
- Editing ThirdParty/ — never modernize vendored upstream code.
- Removing `(void)` from a real C header — there it is required.
