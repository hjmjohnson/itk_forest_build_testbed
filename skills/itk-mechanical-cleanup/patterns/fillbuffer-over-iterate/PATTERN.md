---
pattern: fillbuffer-over-iterate
itk_main_status: none
scope: all
---

## Overview

`itk::Image::FillBuffer(value)` writes the pixel buffer with a single
contiguous `std::fill`. An iterator loop that visits every pixel only to assign
the same constant does the same job pixel-by-pixel through iterator increments
and bounds checks — slower, and it pulls in an iterator header for no reason.

**Core principle:** when the *entire* buffer is set to one loop-invariant value
and the iterator index is never read, the loop is exactly `FillBuffer` spelled
the long way. Collapse it.

## When to use

- A for/while loop over `ImageRegionIterator` / `ImageRegionIteratorWithIndex`
  (const or not) whose **only** body statement assigns a constant.
- The iterator covers `GetBufferedRegion()` or `GetLargestPossibleRegion()`.
- The assigned value is **loop-invariant** (does not depend on the iterator's
  index/position).

## When NOT to use

- The body reads the iterator index / position, or computes the value from it
  (e.g. `it.Set(it.GetIndex()[0])`) — that is a genuine per-pixel computation.
- The iterator covers a **sub-region** (a crop), not the full buffer —
  `FillBuffer` fills the *whole* buffer, so this would change behavior.
- The loop body has more than the single assignment statement.
- The value changes across iterations (counter, accumulator, RNG draw).

These cases are emitted as **review-only candidates**, never auto-rewritten.

## Before / after

```cpp
for (OutputIterator outIt(output, output->GetBufferedRegion()); !outIt.IsAtEnd(); ++outIt)
{
  outIt.Set(outputPixel);
}
// becomes
output->FillBuffer(outputPixel);
```

The now-unused `using OutputIterator = itk::ImageRegionIterator<...>;` typedef
and its `#include "itkImageRegionIterator.h"` should be dropped if nothing else
in the translation unit uses them.

## Detection

```bash
bash skills/itk-fillbuffer-over-iterate/detect.sh [repo-path]   # default .
```

Pre-filter (what `detect.sh` runs): files where an
`ImageRegion(Const)?Iterator(WithIndex)?` declaration is co-located with a
`.Set(` on a single argument, or a `*it = ` assignment. This over-reports;
every hit must be read to confirm it is a full-buffer constant fill.

## Transformation approach

`transform.sh` rewrites one shape, which it can prove from the text: a
`for` loop whose init declares an `ImageRegionIterator` (or an alias of
one) on `img, img->GetBufferedRegion()` or
`img, img->GetLargestPossibleRegion()`, whose increment is `++it`, and whose
body is the single statement `it.Set(<expr>);`. A `while (!it.IsAtEnd())`
loop is accepted only with two guards: the iterator declaration (and an
optional `it.GoToBegin();`) directly precedes it, so the declaration can be
removed with the loop, and `it` is not used anywhere after the loop in the
enclosing block. Its body must be `it.Set(<expr>); ++it;`. `<expr>` must not mention the iterator,
increment, assign, or call anything except casts, `NumericTraits` constants,
and `...Type(...)` conversions. The loop becomes `img->FillBuffer(<expr>);`.

Every other candidate loop is reported as `SKIPPED` and left for review: a
sub-region, a value read from the iterator, a counter, more than one body
statement, or a comment inside the replaced span. The iterator `using` and
`#include` are left in place; drop them by hand if nothing else uses them.

```bash
bash transform.sh <repo>                                  # dry run
bash transform.sh <repo> --apply [--manifest m.json]      # write
```

## Verification (pattern-specific)

Confirm the image is fully allocated before the original loop — `FillBuffer`
requires an allocated buffer, the same precondition the loop had. If the
touched module has tests, run them: pixel values must be identical.

## Common mistakes

- Rewriting a loop over a **sub-region** — `FillBuffer` ignores the region and
  fills the entire buffer; this silently changes output. Verify the region is
  the full buffered/largest region first.
- Rewriting when the value depends on the index — not a constant fill.
- Leaving the orphaned iterator `#include`/typedef behind (dependency not
  actually dropped) — or deleting an `#include` still used by another loop.
- Assuming `FillBuffer` allocates — it does not; the buffer must already be
  allocated, exactly as the loop required.
