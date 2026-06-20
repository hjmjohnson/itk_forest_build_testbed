---
name: itk-prefer-prefix-increment
description: >-
  Use when modernizing per-pixel / per-element loops in ITK or any ITK consumer
  (ANTs, BRAINSTools, Slicer, elastix, c3d, SimpleITK) to eliminate hidden
  copies from postfix increment/decrement of iterators in discarded-value
  contexts. Targets standalone statements `it++;` / `it--;` and for-loop
  increment clauses `for(...; ...; it++)` where the returned pre-increment
  value is never used. ITK iterators have non-trivial copy ctors, so postfix++
  pays a per-iteration temporary that prefix++ avoids — zero behavioral change.
  Keywords: prefix increment, ++it vs it++, postfix increment performance,
  iterator copy, modernize-loop-convert, performance-for-range-copy, per-pixel
  loop, GoToBegin IsAtEnd loop, discarded-value increment.
---

> **Constraint — C++17, ITKv5 + ITKv6:** target C++17 idioms valid against both ITK >=5.4 and ITKv6; never require C++20+. Verify transformed output by compiling against both ITK header sets with `-std=c++17` (see skills/BRAINSTOOLS_HARDENING.md).

# itk-prefer-prefix-increment

## Overview

Postfix `it++` on a class-type iterator must construct and return a copy of the
iterator's pre-increment state. ITK iterators (ImageRegionIterator,
NeighborhoodIterator, DataObjectIterator, mesh/point iterators, …) have
non-trivial copy constructors, so every postfix increment in a hot loop pays a
hidden temporary. When the returned value is **discarded** — the increment is a
full statement, or the increment clause of a `for` — prefix `++it` is exactly
equivalent in behavior and avoids the copy.

**Core principle:** in any discarded-value context, prefer `++X` over `X++`.
Never touch a postfix increment whose returned value is consumed (e.g.
`a[i++]`, `x = it++`, `f(it++)`).

## When to use

- Auditing/modernizing ITK or a downstream consumer's per-pixel/per-element loops.
- A standalone increment statement: `pointItr++;`
- A `for`-increment clause: `for (It it(this); !it.IsAtEnd(); it++)`
- Broadly mechanizable across the whole forest — zero behavioral risk.

## When NOT to use

- The increment's **return value is used**: `arr[i++]`, `*p++`, `x = it++`,
  `return it++;`, `while (cond) doThing(it++)`. These change meaning if rewritten.
- Scalar loop counters in trivial PODs — harmless but not worth the churn; the
  payoff is class-type iterators with non-trivial copies. (Still safe to apply.)
- ThirdParty/ vendored code (excluded by `detect.sh`).

## Before / after

```cpp
// for-increment clause
for (OutputDataObjectIterator it(this); !it.IsAtEnd(); it++)   // before
for (OutputDataObjectIterator it(this); !it.IsAtEnd(); ++it)   // after

// standalone statement
pointItr++;   // before
++pointItr;   // after
```

## Detection

```bash
bash skills/itk-prefer-prefix-increment/detect.sh <repo>   # default: .
```

Greps `.cxx/.hxx/.h/.cpp/.txx` (via `git grep`, ThirdParty excluded) for two
discarded-value shapes and prints `file:line` hits plus a count:

1. **Standalone statement** — `IDENT++;` / `IDENT--;` as a whole statement.
2. **for-increment clause** — `IDENT++` / `IDENT--` immediately before the `)`
   that closes a `for(...;...;...)` header.

Regex is necessarily approximate. The authoritative discriminator is the AST:

```
# clang-query (run against compile_commands.json)
match unaryOperator(hasOperatorName("++"), isPostfix(),
                    unless(hasParent(expr())))
# overloaded iterator operator++ whose result is unused:
match cxxOperatorCallExpr(hasOverloadedOperatorName("++"),
                          unless(hasParent(expr())))
```

A node whose parent is a `CompoundStmt` (statement context) or the increment of
a `ForStmt` has its value discarded and is safe to flip.

## Transformation approach

Two safe paths; pick by tooling available.

**Preferred — clang-tidy (AST-accurate, no false positives):**

```bash
clang-tidy -p <build-dir> --checks='-*,readability-redundant-*' ...   # n/a
# Use the modernize/perf family that handles this directly:
clang-tidy -p <build-dir> --fix --checks='-*,modernize-loop-convert' <file>
```

There is no upstream check named exactly "prefer-prefix", so for AST-accurate
flips use a clang-query → clang-apply-replacements fix-it, or drive
`run-clang-tidy` with a custom matcher. The matcher above only matches
discarded-value postfix increments, so it cannot rewrite a value-consuming site.

**Mechanical — `transform.sh` (regex, dry-run default):**

```bash
bash skills/itk-prefer-prefix-increment/transform.sh <repo>          # dry-run
bash skills/itk-prefer-prefix-increment/transform.sh <repo> --apply  # write
```

`transform.sh` rewrites only the two unambiguous discarded-value shapes
(`IDENT++;`→`++IDENT;` and `IDENT++)` closing a `for` header → `++IDENT)`),
operating per-file on a copy and only when the line matches the strict pattern.
It never commits. **Review the diff** — regex cannot see macro context, so
inspect hits inside macros before `--apply`.

## Verification

1. `git diff` — every change is `X++`→`++X` or `X--`→`--X`, nothing else.
2. Rebuild the affected target via the forest (ccache keeps it fast):
   `pixi run build-ITK` (or the consumer's `build-<name>`).
3. Confirm the **artifact** exists on disk (lib/binary), not just a green pipe.
4. Optional: re-run `detect.sh` — the discarded-value count should drop to the
   intentional value-consuming sites (which must be 0 after a full pass, since
   those shapes are never emitted by detect.sh).
5. Spot-check a value-consuming postfix (`a[i++]`) was left untouched.

## Common mistakes

- **Flipping a value-consuming postfix** — `arr[i++]`, `*p++`, `x = it++` change
  meaning. `detect.sh`/`transform.sh` deliberately match only statement and
  for-clause shapes; never hand-flip a site whose result is read.
- **Rewriting inside ThirdParty/** — vendored upstream; excluded for a reason.
- **Trusting the pipe exit code** after rebuild — verify the artifact on disk.
- **Running `transform.sh --apply` without reading the dry-run** — a postfix
  inside a macro body can match the line regex while being unsafe in context.
- **Touching `operator++` overload definitions** — `Self operator++(int)` in an
  iterator header is the definition, not a use; detect.sh's `;`/`)` anchoring
  skips signatures, but confirm any header hit is a use site.
