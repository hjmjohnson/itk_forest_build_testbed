---
pattern: iterator-drop-withindex
itk_main_status: none
scope: all
---

## Overview

`ImageRegionIteratorWithIndex` (and its const sibling) maintains a full
`Index` vector that it increments on **every** `operator++`. If the loop body
never asks for that index via `.GetIndex()` / `.GetIndexInternal()`, the index
bookkeeping is pure overhead. `ImageRegionIterator` / `ImageRegionConstIterator`
have identical `Get()`/`Set()`/`IsAtEnd()`/`GoToBegin()` interfaces and are a
drop-in replacement that skips the per-increment index update.

**Core principle:** the swap is safe **only after confirming the iterator
variable's index is never read** within its lifetime. This is a local,
well-bounded use-analysis — but it is real analysis, so this skill is
**flag-then-confirm**, not blind sed.

## When to use

- A perf pass over an ITK filter `.hxx` / `.cxx` where a `WithIndex` iterator
  drives a `Get()`/`Set()` loop and the index is never consumed.
- Recurring ITK PERF campaign cleanup of unnecessary `WithIndex` iterators.

## When NOT to use

- The loop calls `it.GetIndex()` / `it.GetIndexInternal()` (the index IS used —
  keep `WithIndex`).
- The variable is passed to a function/template expecting the `WithIndex` type,
  or its type alias is reused for a second iterator that *does* read the index.
- `ShapedNeighborhood`, `ConstNeighborhood`, `ImageRegionExclusion*`, line
  iterators, or any non-`ImageRegion*IteratorWithIndex` type — out of scope.
- ThirdParty/ — never touched.

## Before / after

```cpp
- #include "itkImageRegionIteratorWithIndex.h"
- ImageRegionIteratorWithIndex<ImageType> it(img, img->GetLargestPossibleRegion());
+ #include "itkImageRegionIterator.h"
+ ImageRegionIterator<ImageType> it(img, img->GetLargestPossibleRegion());
  for (it.GoToBegin(); !it.IsAtEnd(); ++it)
  {
    it.Set(it.Get() * scale);   // never calls it.GetIndex()
  }
```

`ImageRegionConstIteratorWithIndex` -> `ImageRegionConstIterator`, include
`itkImageRegionConstIterator.h`.

## Detection

```bash
bash skills/itk-iterator-drop-withindex/detect.sh [repo-path]   # default .
```

It `git grep`s for `ImageRegion(Const)?IteratorWithIndex<...>` *declarations*
(excludes doc-comment `\sa` lines and ThirdParty/), then for each hit reports
whether the same file contains any `.GetIndex(` / `.GetIndexInternal(` call.
Files with a WithIndex declaration but **no** GetIndex call are CANDIDATEs;
files with both need per-variable review (a file may have two iterators where
only one reads the index).

## Transformation approach

Review-gated, two phases (see `transform.sh`):

1. **Find** each WithIndex declaration and its variable name.
2. **Scan that variable's scope** for `<var>.GetIndex(` / `<var>.GetIndexInternal(`.
   If none, rewrite: drop `WithIndex` from the type and switch the `#include`
   (`itkImageRegionIteratorWithIndex.h` -> `itkImageRegionIterator.h`,
   const variant likewise).

`transform.sh` is **dry-run by default**; `--apply` writes. It only rewrites a
file when *every* WithIndex variable in it is index-free (the safe common
single-loop case). Mixed files are reported for manual edit and left untouched.
It never commits. For maximum rigor, a `clang-query` matcher (`varDecl` typed
as a `*WithIndex` iterator whose `DeclRefExpr`s never reach a `memberCallExpr`
named `GetIndex`) is the preferred confirmation step.

## Verification (pattern-specific)

`Get`/`Set` semantics are identical, so any test delta signals a missed
`GetIndex` use — revert that file. Confirm only the type token and the
`#include` changed.

## Common mistakes

- **Blind sed across a file with two iterators** — one may legitimately read the
  index. Always gate on the per-variable GetIndex scan; `transform.sh` skips
  mixed files for this reason.
- **Forgetting the `#include` swap** — leaving the WithIndex header pulls in the
  heavier class transitively and defeats the cleanup intent; the rewrite changes
  both.
- **Rewriting `using` aliases reused elsewhere** — an alias named `IteratorType`
  may back a second iterator; verify the alias has a single consumer first.
- **Touching `GetIndexInternal()`** sites — that also reads the index; treat it
  exactly like `GetIndex()`.
