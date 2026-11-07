---
name: itk-prefer-const-read-only-iterators
version: 1.0.0
purpose: Find ITK image iterators that are declared writable but only read, and convert them to the Const iterator variants by hand, one subsystem per commit.
description: >-
  Scans a C++ source tree for ITK image iterators (ImageRegionIterator,
  ImageRegionIteratorWithIndex, and the other Image*Iterator classes) that
  are declared writable but never call Set(), Value(), or assign through
  the iterator, then guides the conversion to the Const names
  (ImageRegionConstIterator and so on). The Const names compile unchanged on
  ITK 5.4, 5.4.8, and ITK main, so the same edit works across the forest.
  The scanner only reports; every conversion is made by hand because a
  type alias shared with a writing iterator has to be split and a function
  that receives the iterator may write through it. Use for BRAINSTools,
  ANTs, CaPTk, Plastimatch, ITK itself, or any ITK consumer.

  Trigger when the user mentions: const iterators, read-only iterators,
  ImageRegionConstIterator, writable iterator never written, iterator
  const-correctness, ITK PR 7065, or ITK issue 7003.
triggers:
  - itk-prefer-const-read-only-iterators
  - /itk-prefer-const-read-only-iterators
  - convert read-only iterators to const
  - prefer const iterators
  - ImageRegionConstIterator
user_invocable: true
cmd: false
argument_hint: "<source-root> [--json] [--summary]"
contract:
  inputs:
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: false
    writes_to_repo_paths: []
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: false
    network_required: false
    git_required: false
    user_confirmation_required: false
  determinism: hybrid
  cache:
    has_cache: false
    cache_root:
    schema_version: 0
    rebuildable: true
  derivation:
    has_ai_derived_layer: true
    derivation_version: 1
dependencies:
  skills: []
  external_tools:
    - git
    - pre-commit
  python_packages: []
  scripts:
    - const_iterators.py
deployment:
  tier: always
  target_projects: []
  needs_loader_dir: true
  adapters:
    - claude-code
---

# Prefer const iterators for read-only loops

## Quick reference

If invoked without arguments, print this and ask which source root to scan:

```
itk-prefer-const-read-only-iterators - find writable iterators that only read

Usage:
  /itk-prefer-const-read-only-iterators <root>             List candidates
  /itk-prefer-const-read-only-iterators <root> --summary   Counts only
  /itk-prefer-const-read-only-iterators <root> --json      Machine-readable

Scanner: const_iterators.py in this skill's directory. It never edits files.
```

Run it with `python3 -I <skill-dir>/const_iterators.py scan <root>`. Dot
directories, `build*`, `*-build`, `ThirdParty`, `Utilities`, `ExternalData`,
and `Testing` are skipped, so a Claude worktree under `.claude/` is not
scanned twice.

## Why

A loop that only reads should say so. The compiler then rejects an accidental
write, and a reader does not have to scan the body to learn that the image is
unchanged. A writable iterator also asks for a non-const buffer pointer, which
matters for GPU and CUDA images. On CPU images there is no speed difference:
a 256 cubed sum took 12.1 ms with either iterator on ITK main and on ITK
PR 7065.

## The backward-compatible form

- Use the `Const` names: `itk::ImageRegionConstIterator<T>`,
  `ImageRegionConstIteratorWithIndex<T>`, and the matching names for the
  other iterator classes. They exist in ITK 5.4, 5.4.8, and main. After
  PR 7065 each is a thin class over `XxxIterator<const T>`, so source written
  this way compiles unchanged everywhere.
- Do not write `ImageRegionIterator<const T>` for compatibility. In 5.4 it
  compiles but still allows writes through `const_cast` (issue 7003); the
  enforcement arrives only with PR 7065.
- Constructors take `const TImage *`. A `SmartPointer` or a `GetOutput()` result
  converts implicitly, so change the type name and leave the arguments alone.
- Where a function only reads, also take `const ImageType *`. That is the
  enforcement 5.4 can already give.
- `Get()`, `Value()`, `GetIndex()`, `IsAtEnd()`, `GoToBegin()`, `Begin()`, and
  `++` all exist on the Const classes. `Set()` does not, which is the point:
  a compile error after a conversion means the iterator was not read-only.

## Procedure

1. Start a branch off the project's `main`. Do not work in a forest worktree
   that carries local commits.
2. Scan and read the candidate list. Expect about 80 percent precision.
3. For each candidate, grep every use of the variable in its function before
   converting. Convert only when the body calls nothing but the read methods.
4. Convert by hand, per file. Do not script the edit: the traps below need
   judgment.
5. Build, then run the full test suite. A Const conversion is a type-level
   change, so a clean build plus an unchanged test result is the evidence.
6. Run the scanner again. Only deliberate leftovers should remain.
7. Run `pre-commit run --all-files`; clang-format realigns declarations when
   a type name gets longer.
8. Commit one subsystem per commit with a `STYLE:` subject. The body gives the
   reason once: these loops only read the image. Do not open a PR without an
   explicit request for that PR, and open it as a draft.

## Traps

- **Shared alias.** One `using RegionIteratorType = ...` often serves a read
  iterator and a written one. Add a `ConstRegionIteratorType` alias for the
  read side and leave the original for the writer. The scanner marks these
  candidates "split it".
- **Passed to a function.** The scanner marks iterators handed to a helper
  ("passed to a function"). The helper may write through it, so read the
  helper before converting.
- **Output iterators that look unused.** An iterator that only appears in
  `++` and a pointer escape may feed an FFT or filter buffer. Leave those.
- **Name collisions.** The scanner skips `Class::Iterator` names (histogram
  and container iterators) but a hand-written alias named `Iterator` can still
  hide one. Check the declared type.
- **Iterators over `const` images.** `ImageRegionIterator<const T>` is a
  separate finding (issue 7003). The scanner counts it as
  `writable_over_const_image`; convert it to the Const name as well.
- **Missing includes.** `itkImageRegionIterator.h` includes the Const header in
  5.4, but a header that now names only the Const class should include the
  Const header itself.
- **Unrelated bugs surface.** Reading each loop closely finds old bugs, such
  as a loop condition written `it.IsAtEnd()`. Report them. Do not fix them in
  the conversion commit, because a fix changes behavior and the conversion
  must not.

## Verifying against ITK 5.4 and main

Build and test with both. The forest recipes are
`FOREST_REFERENCE_SUFFIX=itk-release-5.4 pixi run build-<Project>` and
`FOREST_REFERENCE_SUFFIX=itk-main pixi run build-<Project>`. A project that
cannot build against both has not been verified for the claim that the same
source works on every version.

## Scanner notes

- It flags a writable iterator when the file has no `var.Set(`, `var.Value(`,
  `*var =`, or `std::fill/copy/transform` use naming the variable. A variable
  name reused in another function of the same file hides a real write, which
  makes the scanner conservative in that direction.
- It misses iterators created through a factory or a template alias defined in
  another file.
- Aliases are matched by name across the whole file. If two functions define
  the same alias name with different iterator classes, a candidate can be
  attributed to the wrong definition; read the declaration before converting.
- It excludes neighborhood, line, path, mesh, point, cell, list, sample,
  histogram, and shaped iterators.
- Tests live in `tests/test_const_iterators.py` and run with
  `python3 -m unittest discover -s <skill-dir>/tests`.

## Worked example

BRAINSTools, November 2026: a scan of `origin/main` listed 37 candidates. Of
them, 5 were `Imgmath.h` loops sharing one alias, 12 were `itkIOGTest.cxx`
test iterators, and 3 were BRAINSSuperResolution output iterators. The
conversion touched 14 files in five commits, built clean on ITK 5.4.7, and
passed 559 of 559 tests. The scan also found a loop in
`DWIConvertUtils.hxx` whose condition was inverted, which became its own bug
fix.

Inventory across the forest on 2026-11-01: 1,815 writable iterators, 872
Const, and 517 writable but never written (ANTs 237 candidates, CaPTk 301,
Plastimatch 154).

## Related

- ITK PR 7065: const-correct iterators, thin Const classes over
  `XxxIterator<const T>`.
- ITK issue 7003: writes through iterators over const images.
- `itk-const-promote`: promotes const locals; this skill promotes iterators.
- `itk-sizetype-filled`: another one-pattern modernization with a bundled
  scanner.
