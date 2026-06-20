---
name: itk-cstyle-to-static-cast
description: >-
  Use when modernizing ITKv3-era C++ that uses C-style casts — (SizeValueType)x,
  (unsigned char *)buffer, (double)expr, (QEType *)nullptr — into named C++ casts
  (static_cast/reinterpret_cast/const_cast), or when dropping redundant same-type
  casts. Targets the large legacy cast surface in ANTs/BRAINSTools and ITK proper
  so narrowing/signedness conversions become greppable and the compiler can reject
  what C casts silently allow. Keywords: C-style cast, static_cast, named cast,
  google-readability-casting, cppcoreguidelines-pro-type-cstyle-cast, cStyleCastExpr,
  (Type)expr, narrowing conversion, redundant cast, casting modernization.
---

> **Constraint — C++17, ITKv5 + ITKv6:** target C++17 idioms valid against both ITK >=5.4 and ITKv6; never require C++20+. Verify transformed output by compiling against both ITK header sets with `-std=c++17` (see skills/BRAINSTOOLS_HARDENING.md).

# itk-cstyle-to-static-cast

## Overview

Replace C-style casts `(Type)expr` with the appropriate named C++ cast. A C cast
silently picks the most permissive of `static_cast`, `const_cast`, and
`reinterpret_cast` (and combinations), hiding narrowing, signedness, and
const-strip conversions. Named casts make each conversion explicit, searchable,
and subject to compiler diagnostics.

**Core principle:** value/numeric and up/down-cast-in-hierarchy conversions
become `static_cast`; pointer-bit reinterpretations become `reinterpret_cast`;
const-strips get **reviewed, not blindly converted** — ITK's practice is to
*drop* an unnecessary const-strip rather than launder it through `const_cast`.
Redundant casts whose argument already has the target type are deleted outright.

## When to use

- Auditing/modernizing legacy ITK-ecosystem source (ANTs, BRAINSTools, ITK
  proper) that predates `static_cast` discipline.
- A reviewer or `clang-tidy` flags `google-readability-casting` or
  `cppcoreguidelines-pro-type-cstyle-cast`.
- You want narrowing/signedness conversions to be greppable before an
  integer-type or `SizeValueType` change.

## When NOT to use

- ThirdParty/ vendored code (GDCM, DCMTK, KWSys, …) — never touch.
- C source (`.c`) and macros where a C cast is the only portable option.
- `(void)unusedArg;` discard casts — leave them; they are idiomatic and not a
  conversion.
- Const-strip casts — do not auto-convert; route to manual review (see below).

## Before / after

```cpp
- ot.Set((SizeValueType)value);
+ ot.Set(static_cast<SizeValueType>(value));

- ByteSwapper<int>::SwapRangeFromSystemToBigEndian((int *)buffer, n);   // bit reinterpret
+ ByteSwapper<int>::SwapRangeFromSystemToBigEndian(reinterpret_cast<int *>(buffer), n);

- result = (OffsetValueType)(this->GetIndex());   // argument already OffsetValueType
+ result = this->GetIndex();                       // redundant cast dropped
```

## Detection

`detect.sh <repo>` greps for operator-preceded `(Type)operand` C-style casts,
restricted to type-looking targets (scalar keywords + `*Type`/`*ValueType`/
`*Pointer`/`*PixelType`/… suffixes), excluding ThirdParty/ and comment lines.
Raw grep over *all* parenthesized identifiers is too noisy (it matches English
prose and `operator++(int)` parameter lists), so the matcher is boundary-aware.

```bash
bash skills/itk-cstyle-to-static-cast/detect.sh /path/to/repo
```

The **authoritative** detector is the clang AST matcher (no false positives):

```bash
# Needs a compile_commands.json for the tree.
clang-tidy -checks='-*,google-readability-casting' -p <build-with-compdb> <file.cxx>
# Redundant same-type casts: cStyleCastExpr where source/dest canonical types match.
clang-query -p <build> <file.cxx>   # then: m cStyleCastExpr()
```

## Transformation approach

This transform is **review-only / clang-tidy-assisted** — there is no safe
pure-`sed` rewrite (the cast operand can be an arbitrary balanced expression,
and the right named cast depends on the types involved). Two paths:

1. **clang-tidy `--fix` (preferred, where a compile DB exists).** It chooses the
   correct named cast per the AST:
   ```bash
   clang-tidy -p <build-with-compile_commands.json> \
       -checks='-*,google-readability-casting' --fix <file.cxx>
   ```
   Then hand-review every emitted `const_cast` and `reinterpret_cast`: prefer to
   *remove* an unnecessary const-strip rather than keep a `const_cast` (ITK's
   choice). Drop casts whose argument already has the target type.

2. **No compile DB (the forest ITK tree).** `detect.sh` is the deliverable: it
   lists candidate sites for manual conversion. The forest's per-consumer build
   dirs (e.g. `*-build/compile_commands.json`) can feed path (1) for downstream
   projects.

## Verification

- Rebuild the affected target — a wrong named cast (e.g. `static_cast` where a
  reinterpret was meant) fails to compile, which is the point.
- `detect.sh` count drops to (or near) zero for the converted files.
- `git diff` shows no surviving `(Type)` casts except intentional `(void)`
  discards and const-strips deferred to review.

## Common mistakes

- **Blind `(const T*)x` → `const_cast`.** Most legacy const-strips are
  accidental; remove the strip instead of laundering it. Only `const_cast` when
  the strip is genuinely required (calling a non-const legacy API on a const).
- **`reinterpret_cast` vs `static_cast` confusion.** Pointer-to-related-type and
  numeric conversions are `static_cast`; only unrelated-pointer / pointer-bit
  reinterpretations are `reinterpret_cast`.
- **Touching ThirdParty/.** Excluded by `detect.sh`; never modernize vendored
  trees.
- **Rewriting `(void)expr;`.** That is a deliberate discard, not a conversion.
- **Pure-grep + sed mass rewrite.** The operand is a balanced expression; a
  regex will mangle nested parens. Use the AST tool or convert by hand.
