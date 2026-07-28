---
pattern: prefer-prefix-increment
itk_main_status: none
scope: all
---

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

## Verification (pattern-specific)

Spot-check that a value-consuming postfix (`a[i++]`) was left untouched.

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
