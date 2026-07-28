---
pattern: ctad-iterator
itk_main_status: none
scope: all
---

## Overview

C++17 class template argument deduction (CTAD) lets the compiler deduce an
iterator's template arguments from its constructor arguments. ITK's image
iterator classes (ITK >= 5) carry deduction-guide-bearing constructors whose
first argument is the image, so the explicit `<...>` on a construction
expression is redundant and can be deleted.

**Core principle:** delete the `<...>` only on *construction* sites (the
class-name token is immediately followed by `(`), where the first argument is
an image pointer/ref so deduction can succeed — never on a type alias,
declaration, or `typedef`.

## When to use

- Modernizing ITK in-tree `.hxx`/`.cxx` code to the current iterator idiom.
- A construction like `IterType<SomeImageType>(image, region)` where `IterType`
  is one of the closed set and the first arg is an image.
- Survives type renames (the deduced type tracks the argument), matches the
  idiom downstream ITK already uses.

## When NOT to use

- The token after the class name is **not** `(` — e.g. `using It = ImageRegionIterator<T>;`,
  `ImageRegionIterator<T> it;` (declaration), a member-type alias, or a function
  return/parameter type. These need the explicit argument; deleting it breaks.
- The first constructor argument is not an image (cannot deduce).
- ThirdParty/ trees — never touch vendored code.

## Before / after

```cpp
- it = ImageRegionIterator<OutputImageType>(this->GetOutput(), face);
+ it = ImageRegionIterator(this->GetOutput(), face);

- auto iRegIter = ImageRegionConstIterator<InputImageType>(this->GetInput(), requestedRegion);
+ auto iRegIter = ImageRegionConstIterator(this->GetInput(), requestedRegion);
```

## Detection

```bash
bash skills/itk-ctad-iterator/detect.sh <repo-path>   # default .
```

Greps tracked `*.hxx`/`*.cxx` (excluding ThirdParty/) for one of the closed-set
iterator names immediately followed by `<...>(` — the construction shape. Prints
`file:line` hits and a total count.

## Transformation approach

This is **review-only / semi-automatic**. `transform.sh` provides a dry-run
preview and an `--apply` mode for the unambiguous single-line case, but each
hit must still be eyeballed:

- The regex confirms `<...>(` but **cannot prove the first arg is an image**.
  Confirm the construction's first argument is an image pointer/ref before
  accepting the edit.
- Multi-line constructions (template args or args spanning lines) are reported
  by `detect.sh` but skipped by `transform.sh`'s auto mode — edit by hand.
- Nested `<...>` (e.g. `ImageRegionIterator<Image<float,3>>(...)`) is handled by
  balanced-bracket matching in `transform.sh`.

Apply, then re-run clang-format and build:

```bash
bash skills/itk-ctad-iterator/transform.sh <repo-path>            # dry-run
bash skills/itk-ctad-iterator/transform.sh <repo-path> --apply    # write
# then: pre-commit run clang-format --all-files ; pixi run build-ITK
```

## Verification (pattern-specific)

CTAD failures are compile errors, so the build is the proof that deduction
succeeded. Every diff hunk must be a pure deletion of a `<...>` token.

## Common mistakes

- Deleting `<...>` on a declaration (`ImageRegionIterator<T> it;`) — there is no
  argument to deduce from; it won't compile. Only construction (`<...>(`) sites.
- Accepting a hit whose first arg is not an image — deduction fails to compile.
- Editing ThirdParty/ — excluded by detect.sh for a reason; never modernize vendored code.
- Skipping the build — CTAD correctness is only proven by a successful compile,
  not by the grep count alone.
