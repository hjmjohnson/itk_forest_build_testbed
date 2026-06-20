---
name: itk-constexpr-if-constant
description: >-
  Use when an ITK header (.h/.hxx) branches at runtime on a compile-time
  constant — typically `if (Dimension > 2)`, `if (VDimension == 3)`,
  `if (ImageDimension >= 1)`, `if (PointDimension < 4)`, or
  `if (ByteSwapper<T>::SystemIsBigEndian())` — where the condition is a
  constant expression (template non-type parameter, static constexpr member,
  or constexpr function). Migrating these to `if constexpr` enables
  dead-branch elimination and lets the not-taken dimension branch hold
  dimension-specific code without SFINAE. Keywords: if constexpr, constexpr
  if, dimension comparison, VDimension, ImageDimension, dead branch
  elimination, compile-time branch, SystemIsBigEndian.
---

> **Constraint — C++17, ITKv5 + ITKv6:** target C++17 idioms valid against both ITK >=5.4 and ITKv6; never require C++20+. Verify transformed output by compiling against both ITK header sets with `-std=c++17` (see skills/BRAINSTOOLS_HARDENING.md).

# itk-constexpr-if-constant

## Overview

Core principle: when an `if` condition is a **constant expression**, spelling
it `if constexpr` makes the compiler discard the not-taken branch entirely.
The discarded branch is not instantiated, so it may contain code that would
be ill-formed for the actual dimension (e.g. `regionSize[2]` when
`ImageDimension == 2`) without needing SFINAE or tag dispatch.

The high-confidence shape is a comparison of a dimension constant against an
integer literal: `if (VDimension == 3)`. The condition's operands are all
template non-type parameters or `static constexpr` members, so the condition
is a constant expression and `if constexpr` is well-formed.

## When to use / when NOT

Use when:
- The `if` condition compares a dimension constant (`Dimension`, `VDimension`,
  `ImageDimension`, `InputImageDimension`, `OutputImageDimension`,
  `PointDimension`) against an integer literal, and that name resolves to a
  template non-type parameter or `static constexpr` member.
- The condition is `ByteSwapper<T>::SystemIsBigEndian()` or another
  `constexpr` predicate.

Do NOT use when:
- The name shadows the constant with a **runtime** value. ITK has exactly
  this trap: in `itkStatisticsAlgorithm.hxx`,
  `const MeasurementVectorSizeType Dimension = sample->GetMeasurementVectorSize();`
  then `if (Dimension == 0)` — `Dimension` is a runtime local, NOT a
  constant. `if constexpr` here is **ill-formed**. Always confirm the
  operand is constexpr.
- Any operand in the condition is a runtime variable or function call that
  is not `constexpr`.

This transform is **review-only**: detection is reliable, but deciding
whether each operand is a constant expression requires reading the
declaration (or compiling). Do not blanket-`sed`.

## Before / after

```cpp
// itkProxTVImageFilter.hxx — ImageDimension is a static constexpr template constant
- if (ImageDimension == 2)
+ if constexpr (ImageDimension == 2)
  {
    std::ignore = DR2_TV(regionSize[0], ...);
  }

- if (VDimension >= 1)
+ if constexpr (VDimension >= 1)
```

```cpp
// COUNTER-EXAMPLE — do NOT transform (Dimension is a runtime value here)
const MeasurementVectorSizeType Dimension = sample->GetMeasurementVectorSize();
if (Dimension == 0)   // runtime; `if constexpr` would be ill-formed
```

## Detection

```bash
bash skills/itk-constexpr-if-constant/detect.sh <repo>   # default: .
```

Greps `*.h`/`*.hxx` (excluding ThirdParty) for the dimension-comparison and
`SystemIsBigEndian()` shapes, prints `file:line` hits and a count. Each hit
is a **candidate** — verify the operand is constexpr before rewriting.

## Transformation approach

For each candidate, in order of confidence:

1. **Confirm the operand is a constant expression.** Open the declaration:
   - `static constexpr unsigned int ImageDimension = ...;` → constexpr, OK.
   - template `<unsigned int VDimension>` non-type parameter → OK.
   - `static constexpr bool SystemIsBigEndian()` → OK.
   - a local `const ... = someRuntimeCall();` → NOT OK, skip.
2. **Rewrite** `if (...)` → `if constexpr (...)` (and the paired `else if`
   chain, which also becomes `else if constexpr`).
3. **Compile.** A non-constexpr condition makes `if constexpr` ill-formed —
   the compiler is the authoritative gate. The forest build (`pixi run
   build-ITK`) catches this immediately.
4. Re-run `pre-commit run --all-files` / clang-format on touched files.

No automatic rewriter is shipped: the constexpr-ness check is per-site
judgment that a `sed` cannot make safely. `detect.sh` is the deliverable;
apply the edits by hand (or with a clang-query/AST matcher that asserts every
operand is a non-type template parameter or constexpr member).

## Verification

- Build the touched module (`pixi run build-ITK`). `if constexpr` on a
  non-constant condition fails to compile — green build proves every rewrite
  was constexpr-valid.
- Behavior is unchanged: `if constexpr` evaluates the same condition; only
  branch instantiation differs. No new test needed unless the not-taken
  branch previously failed to compile for some dimension.

## Common mistakes

- **Blanket sed over all hits.** The `Dimension == 0` runtime case in
  `itkStatisticsAlgorithm.hxx` is a real false positive — it would break the
  build. Verify constexpr-ness per site.
- **Forgetting `else if` chains.** `if constexpr (D==2) ... else if (D==3)`
  is inconsistent; make the whole chain `else if constexpr`.
- **Adding a comment narrating the change.** The code says what it is;
  `git log` carries the why.
