---
pattern: auto-for-new
clang_tidy_check: modernize-use-auto
itk_main_status: merged
itk_main_ref: de713e7, PR #5570
scope: downstream-and-new-code
---

## Overview

ITK's most pervasive boilerplate is declaring a smart pointer by spelling the
factory type twice:

```cpp
ReaderType::Pointer reader = ReaderType::New();
```

The left-hand type is **identical** to the type returned by `ReaderType::New()`,
so `auto` deduces exactly the same `itk::SmartPointer<ReaderType>` — the rewrite
is lossless:

```cpp
auto reader = ReaderType::New();
```

Core principle: **only rewrite when the LHS type token-equals the RHS
type-before-`::New`** (a regex backreference enforces this). That guard is what
makes the transform safe and mechanical.

## When to use

- Function-local declarations where `T::Pointer name = T::New();`.
- The explicit-Pointer-alias form `const FooPointer name = FooType::New();`
  (where `FooPointer` is a `using FooPointer = FooType::Pointer;` alias) —
  preserve the leading `const`.
- Multi-line wrapped RHS (`auto x =\n  itk::ImageFileReader<T>::New();`) — join,
  then re-run clang-format.

## When NOT to use

- The LHS type differs from the RHS factory type (covariant assignment, base
  pointer from derived `New()`) — `auto` would change the static type. The
  backreference guard already excludes these; never override it.
- **Member declarations** (class fields). `auto` is not allowed for non-static
  data members; restrict to function-local scope.
- ThirdParty/ trees (excluded by `detect.sh`).
- Where an explicit interface type is deliberate documentation the project wants
  kept — review-only judgment call.

## Before / after

```cpp
- ReaderType::Pointer reader = ReaderType::New();
+ auto reader = ReaderType::New();

- const GaussianFilterPointer filter = GaussianFilterType::New();
+ const auto filter = GaussianFilterType::New();

- itk::ImageFileReader<ImageType>::Pointer reader =
-   itk::ImageFileReader<ImageType>::New();
+ auto reader = itk::ImageFileReader<ImageType>::New();
```

## Detection

`detect.sh <repo>` (default `.`) uses `git grep` with pathspecs (glob-safe,
ThirdParty excluded) to find sites where the type before `::Pointer` equals the
type before `::New()` via a backreference:

```bash
bash skills/itk-auto-for-new/detect.sh /path/to/ITK
```

Prints `file:line` hits plus a total count. The alias form
(`const FooPointer x = FooType::New();`) is reported separately since its LHS is
an alias, not a `::Pointer`, and warrants a quick eyeball before rewriting.

## Transformation approach

Two safe options:

1. **clang-tidy (preferred for whole-tree):**
   ```bash
   clang-tidy -p <build-dir> --checks='-*,modernize-use-auto' \
       --config="{CheckOptions: [{key: modernize-use-auto.MinTypeNameLength, value: '0'}]}" \
       --fix <files...>
   ```
   AST-accurate; only rewrites when the initializer type matches. Requires a
   `compile_commands.json`. Does not touch member declarations.

2. **`transform.sh` (regex, no build dir needed):** dry-run by default; `--apply`
   to write. It rewrites only the backreference-guarded `::Pointer` form and the
   `const <Alias>` form, preserves a leading `const`, joins a wrapped RHS, and
   leaves the `= <Type>::New();` RHS intact. It never edits headers' member
   sections (it skips lines lacking a `= ...::New()` initializer on the same or
   next line) and never commits. After the rewrite it sweeps any function-local
   `using FooPointer = T::Pointer;` (or typedef) alias it just orphaned, deleting
   it only when the alias name occurs exactly once in the file (its own
   definition). This prevents the dead-alias `-Wunused-local-typedefs` failure
   GCC raises but Clang's default flags miss (PR #608).

   ```bash
   bash skills/itk-auto-for-new/transform.sh /path/to/ITK            # dry-run diff
   bash skills/itk-auto-for-new/transform.sh /path/to/ITK --apply    # write in place
   ```

Always re-run `clang-format` (or `pre-commit run clang-format`) after either
path; joining a wrapped RHS changes line length.

## Verification (pattern-specific)

A clean build over the rewritten tree is the artifact: if `auto` deduced a
different type it would fail to compile. Run `itk-compile-gate.sh` before
committing — a default build passes an orphaned alias, but the gate makes
`-Wunused-local-typedefs` fatal and prefers GCC, matching the dashboards.

## Common mistakes

- **Rewriting covariant assignments** (`Base::Pointer p = Derived::New();`).
  The backreference guard excludes these; do not loosen it to catch "more" sites.
- **Touching member declarations** — `auto` data members don't compile. Keep the
  transform function-local.
- **Dropping a leading `const`** — `const auto x` must stay `const auto x`.
- **Forgetting clang-format after joining a wrapped RHS** — leaves an
  over-length or oddly-wrapped line that pre-commit will then re-modify.
- **Trusting the regex over the compiler** — verify by rebuilding, not by the
  before/after grep delta alone.
