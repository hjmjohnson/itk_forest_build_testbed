---
pattern: redundant-void-arg
clang_tidy_check: modernize-redundant-void-arg
itk_main_status: merged
itk_main_ref: marked DONE
scope: downstream-and-new-code
---

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

## Verification (pattern-specific)

A clean build confirms no function-pointer typedef or C-interop site was
wrongly rewritten. Remaining detector hits are the legitimate ones.

## Common mistakes

- Running `sed` blindly — strips `(void)` from function-pointer typedefs and
  `extern "C"` prototypes, breaking C interop. Use clang-tidy.
- Editing ThirdParty/ — never modernize vendored upstream code.
- Removing `(void)` from a real C header — there it is required.
